import asyncio
import time
import array
import json
import gc
from random import randrange
import machine


from minilog import getLogger
import pinout
import config
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
 

# This is a singleton class to contain the definition for solenoid MIDI
class SolenoidDef:
    def __init__( self ):

        self.pin_functions = midi.MIDIdict()
        self.pin_names = midi.MIDIdict()
        self.device_info = {}
    
        self._current_i2c = None
        self._current_i2c_number = -1
        self._current_mcp23017 = None
        self._current_mcp_number = None
  
    
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
        if pinout.testI2Cconnected( sda, scl ) != (True, True):
            logger.error( f"No I2C connected {sda=} {scl=}")
            self._current_i2c = None
            self.device_info[device_name] = "not connected"
        else:
            self._current_i2c = machine.SoftI2C( sclpin, sdapin, freq=100_000 )
            self.device_info["i2c" + str( self._current_i2c_number ) ] = "ok"
            
    def define_mcp23017( self, address ):
        self._current_mcp_number += 1
        mcpid = "i2c" + str(self._current_i2c_number) + ".mcp." + str(self._current_mcp_number)
        if address and self._current_i2c:
            logger.debug(f"Try MCP23017 {self._current_i2c=} {address=}")
            try:
                self._current_mcp23017 = MCP23017( self._current_i2c, address )
                self.device_info[mcpid] = "ok"
            except OSError as e:
                logger.exc( e, f"I2C {self._current_i2c_number} MCP {self._current_mcp_number} not found, disabled")
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

def _init( ):
    
    global logger, solenoid_def
    global sumsolenoid_on_msec, solenoid_on_msec
    logger = getLogger(__name__)
    logger.debug("start _init solenoid")
    solenoid_def = SolenoidDef()
                            
    solenoid_on_msec = midi.MIDIdict()
                            
    for m in pinout.all_valid_midis:
        solenoid_on_msec[m] = 0
    sumsolenoid_on_msec = 0
    
    pinout.define_solenoids( solenoid_def )

    all_notes_off()     
    logger.debug(f"init complete {solenoid_def.device_info=}")
    
def all_notes_off( ):
    for midi_note in pinout.all_valid_midis:
        note_off( midi_note )

async def clap( n, clap_interval_msec=50 ):
    logger.debug(f"clap {n}" )
    for _ in range(n):
        midi_note = pinout.all_valid_midis[ randrange(0,len(pinout.all_valid_midis)) ]
        note_on( midi_note )
        await asyncio.sleep_ms(clap_interval_msec)
        note_off( midi_note )
        await asyncio.sleep_ms(clap_interval_msec)

def note_on( midi_note ):
    
    if midi_note not in solenoid_def.pin_functions:
        return
    solenoid_def.pin_functions[midi_note]( 1 )
    # Record time of note on, note_off will compute time this solenoid was "on"
    if solenoid_on_msec[midi_note] == 0:
        solenoid_on_msec[midi_note] = time.ticks_ms()

def note_off( midi_note ):
    global sumsolenoid_on_msec

    if midi_note not in solenoid_def.pin_functions:
        return
    solenoid_def.pin_functions[midi_note]( 0 )
    # Compute time this note was on, add to battery use
    t0 = solenoid_on_msec[midi_note] 
    # Ignore if note was never turned on
    if t0 != 0:
        sumsolenoid_on_msec +=  time.ticks_diff( time.ticks_ms(), t0 )
        solenoid_on_msec[midi_note] = 0

def get_sum_msec_solenoids_on_and_zero():
    global sumsolenoid_on_msec
    t = sumsolenoid_on_msec
    sumsolenoid_on_msec = 0
    return t

def get_status( ):
    return solenoid_def.device_info

def get_pin_name( midi_note ):
    return solenoid_def.pin_names.get( midi_note, "" )

                


_init()

