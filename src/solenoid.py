# (c) 2023 Hermann Paul von Borries
# MIT License
# Solenoid note on/note off, hides difference between GPIO and MCP23027
# Uses MIDIdict to search efficently for the pin function given a MIDI Note
import asyncio
from time import ticks_diff, ticks_ms
import machine
from random import randrange
from collections import OrderedDict
from array import array

from minilog import getLogger
import pinout
from config import config
from midi import controller
from led import led

from mcp23017 import MCP23017

_logger = getLogger(__name__)


class simulated_MCP23017:
    # If there are problems with the real MCP23017
    # use this class to save the day
    def __init__(self):
        pass

    def __getitem__(self, p):
        return self

    def output(self, val=None):
        return val


class SolenoidDef(pinout.PinoutParser):
    # This class parses the pinout.json file to extract
    # the information about pins needed for the solenoid driver
    # and also feeds the midi.Controller with information
    # about midi notes and their relation with SolePin objects
    def __init__(self):
        # The result of the parse is:
        # pin_list: a the complete list of SolePin objects
        # device_info: information to show to the user.
        # These two will be accessed by Solenoid as property
        # Start parsing this pinout.json file
        super().__init__(None)
    
    def define_start( self ):
        self.pin_list = []
        self.device_info = OrderedDict()

        self._current_i2c = None
        self._current_i2c_number = -1
        self._current_mcp23017 = None
        self._current_mcp_number = None
        controller.define_start()

    def define_gpio_midi(self, gpio_pin, midi_note, rank, register_name ):
        if not midi_note.is_valid():
            return
        
        # Define function with closure to set/reset GPIO pins
        pin = machine.Pin(gpio_pin, machine.Pin.OUT)
        name = f"gpio.{gpio_pin}"
        solepin = self.solepin_factory( lambda v, gpiofun=pin.value: gpiofun(v), 
            name, rank, midi_note )
        controller.define_note( midi_note, solepin, register_name  ) 

    # define_register is defined in pinout.py/GPIOdef, not here 
        

    def define_i2c(self, sda, scl):
        self._current_i2c_number += 1
        self._current_mcp_number = -1

        sclpin = machine.Pin(scl)
        sdapin = machine.Pin(sda)

        device_name = "i2c" + str(self._current_i2c_number)
        if pinout.test.testI2Cconnected(sda, scl) != (True, True):
            _logger.error(f"No I2C connected {sda=} {scl=}")
            self._current_i2c = None
            self.device_info[device_name] = "not connected"
        else:
            self._current_i2c = machine.SoftI2C(sclpin, sdapin, freq=100_000)
            self.device_info[device_name] = "ok"

    def define_mcp23017(self, address):
        self._current_mcp_number += 1
        mcpid = (
            "i2c"
            + str(self._current_i2c_number)
            + ".mcp."
            + str(self._current_mcp_number)
        )
        if address is not None and self._current_i2c:
            _logger.debug(f"Try MCP23017 {self._current_i2c=} {address=}")
            try:
                self._current_mcp23017 = MCP23017(self._current_i2c, address)
                self.device_info[mcpid] = "ok"
            except OSError as e:
                _logger.exc(
                    e,
                    f"MCP23027 {mcpid} not found, disabled",
                )
                self.device_info[mcpid] = "ok"
                self._current_mcp23017 = simulated_MCP23017()
        else:
            # Insert simulated MCP23017 to avoid crashing system
            self._current_mcp23017 = simulated_MCP23017()
            self.device_info[mcpid] = "not connected"

    def define_mcp_midi(self, mcp_pin, midi_note, rank, register_name ):
        if not midi_note.is_valid():
            return

        # Define function with closure to change value
        # of MCP23017 port
        # Assign pin description
        name =  f"mcp.{self._current_i2c_number}.{self._current_mcp_number}.{mcp_pin}"
        solepin = self.solepin_factory( lambda v, mpfun=self._current_mcp23017[mcp_pin].output: mpfun(v), 
            name, rank, midi_note )
        
        controller.define_note( midi_note, solepin, register_name )
   

    def define_complete( self ):
        controller.define_complete()

        if not self.pin_list:
            _logger.error("Pin count is 0")
            return

        # Organ tuner uses pin index (index to pin_list)
        # So for organ tuner it's nicer to sort by midi number
        # Also: for polyphony, bass notes are turned off first (that's preferrable to melody notes)
        self.pin_list.sort( key=lambda solepin: solepin.midi_note.midi_number )
        _logger.debug(f"{len(self.pin_list)} solenoids defined")

    def solepin_factory( self, pin_function, name, rank, midi_note):
        for solepin in self.pin_list:
            if solepin.name == name:
                return solepin
        solepin = SolePin( pin_function, name, rank, midi_note )
        self.pin_list.append( solepin )
        return solepin
    
    # Methods to return what's useful 
    def get_pin_list( self ):
        return self.pin_list
    
    def get_device_info( self ):
        return self.device_info

class SolenoidDriver:
    # Solenoid driver
    def __init__(self, max_polyphony):

        # Inform the controller that this is the solenoid driver
        controller.set_solenoid_driver( self )
        # max_polyphony Controls maximum number of notes to sound simultaneously
        # so that the total current current doesn't exceed a limit.
        self.max_polyphony = max_polyphony
        self.polyphony = 0

        # Parsing fills these definitions:
        # pin_list: a list of all SolePins (solenoid pins) that have been defined
        # in the pinout.
        self.pin_list = []
        # device_info is info about MCP devices, to show to the user.
        self.device_info = {}
        # Parse pinout.json
        self.init_pinout()
         
        self.sumsolenoid_on_msec = 0
        self.solenoid_on_time = array("i", (0 for _ in range(len(self.pin_list))))

        self.all_notes_off()
        _logger.debug(f"init complete {self.device_info=}")

    def all_notes_off(self): 
        for solepin in self.pin_list:
            solepin.off()
        self.polyphony = 0

    async def play_random_note(self, duration_msec):
        if (n := self.get_pin_count()):
            solepin = self.pin_list[ randrange( n ) ]
            solepin.on()
            await asyncio.sleep_ms(duration_msec)
            solepin.off()

    async def clap(self, n):
        _logger.debug(f"clap {n}")
        for _ in range(n):
            await self.play_random_note(50)

    def compute_polyphony( self, on_off ):
        # Increment/decrement polyphony counter.
        # Should never go below 0
        self.polyphony = max( self.polyphony + on_off, 0)
        
        if self.polyphony > self.max_polyphony:
            # Exceeding polyphony could lead to battery overload

            # Blink led
            led.short_problem()
            # This can be checked with on a PC later

            # Turn off the oldest note. This code will
            # only act if maximum polyphony is exceeded
            now = ticks_ms()

            # The default value of max() should not happen, it is to prevent
            # a (very unlikely) ValueError
            oldest_time = max(
                (ticks_diff(p.on_time, now)
                for p in self.solepins_that_are_on()),
                default=-1 
            )
            # Turn off the oldest note(s)
            for solepin in self.pin_list:
                # Turn off all solepins that have been on the longest time
                if ticks_diff(solepin.on_time, now) >= oldest_time:
                    # This call to solepin.off() could make this method to
                    # recur if polyphony still exceeded.
                    solepin.off()
                    return
 
    def solepins_that_are_on( self ):
        return set( solepin for solepin in self.pin_list if solepin.on_time>=0 )

    def add_on_time( self, msec ):
        # Keep tally of time solenoids were on
        self.sumsolenoid_on_msec +=  msec      
        
    def get_sum_msec_solenoids_on_and_zero(self):
        t = self.sumsolenoid_on_msec
        self.sumsolenoid_on_msec = 0
        return t

    def get_status(self):
        # Get summary of current devices for display
        return self.device_info

    def get_solepin_by_pin_index(self, pin_index):
        # organtuner.py refers to a pin with it's index
        # in the pin_list. Since the organtuner's pin_index
        # is derived from the pin_list, this works, since
        # solenoids.py and organtuner.py are based on this self.pin_list.
        # organtuner.py synchronizes with self.pin_list
        # at each reboot.
        return self.pin_list[pin_index]
    
    def get_all_pins( self ):
        # Used by organtuner.py to populate organtuner.json
        return self.pin_list

    def get_pin_count( self ):
        return len( self.pin_list )
    
    def init_pinout(self):
        # Called during initialization, and also from webserver 
        # when pinout is changed by the user.
        
        # Parse pinout json to define solenoid pins
        solenoid_def = SolenoidDef()

        # save needed info
        self.pin_list = solenoid_def.get_pin_list()
        self.device_info = solenoid_def.get_device_info()
        # now solenoid_def is discarded, all info is in 
        # SolePin, Controller and Register objects, and
        # self.pin_list and self.device_info

    def reinit( self ):
        global solenoids
        controller.reinit()
        solenoids = SolenoidDriver(config.cfg["max_polyphony"])


class SolePin:
    # A single pin (GPIO or MCP23017) used to drive a solenoid valve
    # pin_function: call this to set pin to high/low
    # name: a unique description to show to user based on note and program number
    # rank: supplied by user in pinout.html
    # midi_note: the midi note number, used for tuning

    # Must have same interface than midi.Drum() (except __init__)
    def __init__( self, pin_function, name, rank, midi_note ):
        # .name, .rank, .midi_note and .on_time are read
        # as properties, no @property defined here to save a bit of space/overhead
        # name: mcp.1.0.11 or gpio13
        # rank: supplied on pinout.html page
        # pin function: call with (0) to turn off, with (1) to turn off
        # midi_note: a NoteDef() object supplied on the pinout.html page
        self.name = name
        self.rank = rank 
        self.pin_function = pin_function 
        self.midi_note = midi_note 
        self.midi_number = midi_note.midi_number

        # on_time is the ticks_ms when the note
        # was turned on. -1 means "solenoid off"
        # self.on_time is accessed directly from SolenoidDriver. It is used
        # to compute battery power usage and polyphony.
        self.on_time = -1

    def on( self ):
        # Set to on only when currently off
        if self.on_time < 0:
            # Turn pin on
            self.pin_function(1)
            # Record time when it was set on
            self.on_time = ticks_ms()
            # One more solenoid on now
            solenoids.compute_polyphony( 1 )


    def off( self ):
        # Set to off only when currently on
        if self.on_time >= 0:
            # Set to off
            self.pin_function(0)
            # Accumulate time a solenoid was on
            solenoids.add_on_time(  ticks_diff(ticks_ms(), self.on_time) )
            # Remember that the pin is now off
            self.on_time = -1
            # One less solenoid on now
            solenoids.compute_polyphony( -1 )

    def is_on( self ):
        return self.on_time >= 0
 
    def get_rank_name( self ):
        return self.name + " " + self.rank
    
    
  
solenoids = SolenoidDriver(config.cfg["max_polyphony"])
