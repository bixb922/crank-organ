# Copyright (c) 2023 Hermann von Borries
# MIT license
#  
from time import ticks_ms, ticks_diff


class BaseDriver:
    def set_actuator_bank( self, actuator_bank ):
        self._actuator_bank = actuator_bank

    def __repr__( self ):
        # Must be unique!!!
        return type(self).__name__.replace("Driver", "")
    
class BasePin:
    # Abstract class for driver_*.py MIDI device actuator drivers
    # Represents a single pin/actuator (GPIO or MCP23017 or PCA9685 or MIDI serial virtual pin)
    # used to drive a solenoid, RC controller (future) or other actuator
    # Has functionality common for all ways to move a pin
    # such as calculation of polyphony.
    # The subclass must implement at least the following methods:
    #   __init__(), if implemented should call super().__init__()  
    #   value(): call this to turn on/off the actuator
    
    def __init__( self, driver, pin, rank, nominal_midi_note ):
        # .name, .rank, .midi_note are read
        # as properties, no @property defined here to save a bit of space/overhead
        # name: mcp.1.0.11 or gpio13
        # rank: supplied on pinout.html page, a text description
        # nominal_midi_note: a NoteDef() object supplied on the pinout.html page
        self._driver = driver
        self._pin = pin
        self._rank = rank      
        self.nominal_midi_note = nominal_midi_note 
        self.nominal_midi_number = nominal_midi_note.midi_number
        
        # self._count is the number of note_on received, minus
        # the number of note_offs, but is never allowed to go negative.
        self._count = 0
        # self._start_time is the last time when an actuator has been turned on..
        
    def on( self ):
        # Set to on only when currently off
        if self._count == 0:
            # Turn pin on
            self.value(1)  # type:ignore
            # Record time when it was set on
            self._start_time = ticks_ms()
            # Add to active list
            self._actuator_bank.add_active( self )
        # Count this "note on" event, to be able to pair note on/off
        # and to be able to turn off the pin when all note offs have
        # been matched.
        self._count += 1


    def off( self ):
        # Set to off only when currently on and this the last note on
        # pending on this pin
        if self._count == 1:
            # Set to off
            self.value(0)  # type:ignore
            # Accumulate time a solenoid was on
            self._actuator_bank.add_operating_time(  ticks_diff(ticks_ms(), self._start_time) )     
            # Remove from active list
            self._actuator_bank.remove_active( self )
        # Do not allow count to go negative, meaning: ignore
        # if there are more note offs than note ons.
        self._count = max(0, self._count-1)

    def force_off( self ):
        # Force off, even if note on and note off don't match
        # But don't turn off if already off.
        if self._count > 0:
            self._count = 1
            self.off()

    def get_rank_name( self ):
        return self._rank
    
    def __repr__( self ):
        # Must be unique!!!! This can be used as key in a dictionaries.
        return  f"{str(self._driver)}.{self._pin}"

    def set_actuator_bank( self, actuator_bank ):
        self._actuator_bank = actuator_bank
     