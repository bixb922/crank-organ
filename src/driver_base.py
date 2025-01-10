# Copyright (c) 2023 Hermann von Borries
# MIT license

from time import ticks_ms, ticks_diff

def singleton(cls):
    instance = None
    def getinstance(*args, **kwargs):
        nonlocal instance
        if instance is None:
            instance = cls(*args, **kwargs)
        return instance
    return getinstance


class BaseDriver:
    
    def set_actuator_bank( self, actuator_bank ):
        self._actuator_bank = actuator_bank

    def __repr__( self ):
        # Must be unique!!!
        return type(self).__name__.replace("Driver", "")
    
class BasePin:
    # Abstract class for driver_*.py MIDI device actuator drivers
    # A single pin (GPIO or MCP23017 or PCA9685 or MIDI serial virtual pin)
    # used to drive a solenoid, RC controller (future) or other actuator
    # Has functionality common for all ways to move a pin
    # such as calculation of polyphony.

    # value: call this to set pin to high/low
    # name: a unique description to show to user based on note and program number
    # rank: supplied by user in pinout.html
    # nominal_midi_note: the midi note number, used for tuning only
    # because organtuner.py tunes by pin, not by MIDI note
    # The reason for this distinction is is that when a MIDI note is played, registers
    # can alter the pin that has to play, and when tuning,
    # registers should not influence tuning.

    # Must have same interface than midi.Drum() (except __init__)
    def __init__( self, driver, pin, rank, nominal_midi_note ):
        # .name, .rank, .midi_note and .on_time are read
        # as properties, no @property defined here to save a bit of space/overhead
        # name: mcp.1.0.11 or gpio13
        # rank: supplied on pinout.html page, a name for the user
        # pin function: call with (0) to turn off, with (1) to turn on
        # midi_note: a NoteDef() object supplied on the pinout.html page
        self._driver = driver
        self._pin = pin
        self._rank = rank 
        
        self.nominal_midi_note = nominal_midi_note 
        self.nominal_midi_number = nominal_midi_note.midi_number
        
        # on_time is the ticks_ms when the note
        # was turned on. -1 means "solenoid off"
        # For efficiency,
        # self.on_time is accessed directly from SolenoidDriver. It is used
        # to compute battery power usage and polyphony.
        self.on_time = -1

    
    def on( self ):
        # Set to on only when currently off
        if self.on_time < 0:
            # Turn pin on
            self.value(1)
            #print(f">>>{type(self).__name__} {self.nominal_midi_note} on")
            # Record time when it was set on
            self.on_time = ticks_ms()
            # One more solenoid on now
            self._actuator_bank.compute_polyphony( 1 )


    def off( self ):
        # Set to off only when currently on
        if self.on_time >= 0:
            # Set to off
            self.value(0)
            #print(f">>>{type(self).__name__} {self.nominal_midi_note} off")
            # Accumulate time a solenoid was on
            self._actuator_bank.add_on_time(  ticks_diff(ticks_ms(), self.on_time) )
            # Remember that the pin is now off
            self.on_time = -1
            # One less solenoid on now
            self._actuator_bank.compute_polyphony( -1 )


    def is_on( self ):
        return self.on_time >= 0
 
    def get_rank_name( self ):
        return self._rank
    
    def __repr__( self ):
        # Must be unique!!!!
        return  f"{str(self._driver)}.{self._pin}"

    def set_actuator_bank( self, actuator_bank ):
        self._actuator_bank = actuator_bank
     