# (c) 2023 Hermann Paul von Borries
# MIT License
# Solenoid note on/note off, hides difference between GPIO and MCP23027
# Uses MIDIdict to search efficently for the pin function given a MIDI Note
import asyncio
import time
import array
import json
import gc
import machine


from minilog import getLogger
_logger = getLogger( __name__ )
import pinout
from config import config
import midi

from mcp23017 import MCP23017

class simulated_MCP23017:
    def __init__( self, i2c, address ):
        pass
    def pin( self, p, value=None ):
        pass
    def __getitem__( self, p ):
        return self
    def output(self, val=None):
        return val
 

# This is a singleton class to hold the definition for solenoid MIDI
class SolenoidPins( pinout.PinoutParser ):
    def __init__( self ):

        self.pin_functions = midi.MIDIdict()
        self.pin_names = midi.MIDIdict()
        self.device_info = {}
    
        self._current_i2c = None
        self._current_i2c_number = -1
        self._current_mcp23017 = None
        self._current_mcp_number = None
        # Start parsing with current definition
        super().__init__( None )
    
    def define_gpio_midi( self, gpio_pin,  midi_note, rank ):
        if not midi_note:
            return

        # Use a closure to define function to set/reset pins
        pin = machine.Pin( gpio_pin, machine.Pin.OUT )
        self.pin_functions[midi_note] = lambda v, gpio=pin : gpio.value(v)
        # Assign pin description
        self.pin_names[midi_note] = f"{rank} gpio.{gpio_pin}" 


    def define_i2c( self, sda, scl ):
        self._current_i2c_number += 1
        self._current_mcp_number = -1

        sclpin = machine.Pin( scl )
        sdapin = machine.Pin( sda )
        
        device_name = "i2c" + str(self._current_i2c_number) 
        if pinout.test.testI2Cconnected( sda, scl ) != (True, True):
            _logger.error( f"No I2C connected {sda=} {scl=}")
            self._current_i2c = None
            self.device_info[device_name] = "not connected"
        else:
            self._current_i2c = machine.SoftI2C( sclpin, sdapin, freq=100_000 )
            self.device_info["i2c" + str( self._current_i2c_number ) ] = "ok"
            
    def define_mcp23017( self, address ):
        self._current_mcp_number += 1
        mcpid = "i2c" + str(self._current_i2c_number) + ".mcp." + str(self._current_mcp_number)
        if address and self._current_i2c:
            _logger.debug(f"Try MCP23017 {self._current_i2c=} {address=}")
            try:
                self._current_mcp23017 = MCP23017( self._current_i2c, address )
                self.device_info[mcpid] = "ok"
            except OSError as e:
                _logger.exc( e, f"I2C {self._current_i2c_number} MCP {self._current_mcp_number} not found, disabled")
                self.device_info[mcpid] = "ok"
                self._current_mcp23017 = simulated_MCP23017( self._current_i2c, address )
        else:
            self._current_mcp23017 = simulated_MCP23017( self._current_i2c, address )
            self.device_info[mcpid] = "test"



    def define_mcp_midi( self, mcp_pin,  midi_note, rank ):
        if not midi_note:
            return

        self.pin_functions[midi_note] = lambda v, m=self._current_mcp23017, p=mcp_pin : m[mcp_pin].output(v)

        # Assign pin description
        self.pin_names[midi_note] = f"{rank} mcp.{self._current_i2c_number}.{self._current_mcp_number}.{mcp_pin}"        
        self.pin_names[midi_note] = f"{rank} mcp.{self._current_i2c_number}.{self._current_mcp_number}.{mcp_pin}"        

class Solenoid:
    def __init__( self ):
        _logger = getLogger(__name__)
        _logger.debug("start _init solenoid")
        self.init_pinout()

        self.solenoid_on_msec = midi.MIDIdict() 
        for m in pinout.midinotes.get_all_valid_midis():
            self.solenoid_on_msec[m] = 0
        self.sumsolenoid_on_msec = 0

        self.all_notes_off()     
        _logger.debug(f"init complete {self.solenoid_def.device_info=}")

    def all_notes_off( self ):
        for midi_note in pinout.midinotes.get_all_valid_midis():
            self.note_off( midi_note )

    async def play_random_note( midi_note, duration_msec ):
        midi_note = pinout.midinotes.get_random_midi_note()
        self.note_on( midi_note )
        await asyncio.sleep_ms(duration_msec)
        self.note_off( midi_note )
        await asyncio.sleep_ms(duration_msec)  
        
    async def clap( self, n, clap_interval_msec=50 ):
        _logger.debug(f"clap {n}" )
        for _ in range(n):
            self.play_random_note( clap_interval_msec )

    def note_on( self, midi_note ):

        if midi_note not in self.solenoid_def.pin_functions:
            return
        self.solenoid_def.pin_functions[midi_note]( 1 )
        # Record time of note on, note_off will compute time this solenoid was "on"
        if self.solenoid_on_msec[midi_note] == 0:
            self.solenoid_on_msec[midi_note] = time.ticks_ms()

    def note_off( self, midi_note ):
        if midi_note not in self.solenoid_def.pin_functions:
            return
        self.solenoid_def.pin_functions[midi_note]( 0 )
        # Compute time this note was on, add to battery use
        t0 = self.solenoid_on_msec[midi_note] 
        # Ignore if note was never turned on
        if t0 != 0:
            self.sumsolenoid_on_msec +=  time.ticks_diff( time.ticks_ms(), t0 )
        self.solenoid_on_msec[midi_note] = 0

    def get_sum_msec_solenoids_on_and_zero( self ):
        t = self.sumsolenoid_on_msec
        self.sumsolenoid_on_msec = 0
        return t

    def get_status( self ):
        return self.solenoid_def.device_info

    def get_pin_name( self, midi_note ):
        return self.solenoid_def.pin_names.get( midi_note, "" )

    def init_pinout( self ):
        # Called during initialization and from webserver when
        # changing pinout
        # Parse pinout json to define solenoid midi to pin
        self.solenoid_def = SolenoidPins()

solenoid = Solenoid()

