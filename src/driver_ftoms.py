# Copyright (c) 2023-2025 Hermann von Borries
# MIT license

from time import sleep_ms

import fileops
from drehorgel import config
import midi
from driver_base import BaseDriver, BasePin, SolePin
from actuatorstats import ActuatorStats

# Does not need to be declared singleton. Since __repr__ is
# defined in BaseDriver, it is unique.
class FauxTomDriver(BaseDriver):
    ft_pin_list = []
    def __init__( self, actuator_bank ):
        self.actuator_bank = actuator_bank
        # Call super().__init__ with no arguments to get repr() right!
        super().__init__()


        ddef = fileops.read_json( config.DRUMDEF_JSON, default={})
        # Need the midi numbers used as key be an int
        self.drum_def = { int(k): v for k, v in ddef.items() if not k.startswith("comment" )}

    @classmethod
    def save( cls, new_drumdef ):
        fileops.write_json( new_drumdef, config.DRUMDEF_JSON )

    # Provide iterator for all defined drums
    # This is different from other drivers. Usually
    # the midi notes are defined in the pinout.json whereas
    # here they are defined in drumdef.json
    def __iter__( self ):
        self.iter_drums = iter(self.drum_def.keys())
        return self
    
    def __next__( self ):
        # Return a new VirtualDrumPin() object for each iteration
        midi_number = next( self.iter_drums )
        dd = self.drum_def[midi_number]
        vdp = VirtualDrumPin( self, midi_number, dd )
        FauxTomDriver.ft_pin_list.append( vdp )
        return vdp
    
    @classmethod
    def get_pin_list( cls ):
        # Used by webserver in a function to test drum defs.
        return FauxTomDriver.ft_pin_list

# Virtual drum pin, virtual because it's not a hardware pin
# and pin because it must have the BasePin interface
class VirtualDrumPin(BasePin):
    # Must have same interface as driver pins (except __init__)
    def __init__( self, driver, midi_number, dditem ):
        super().__init__( driver, midi_number, "Simulated drum", midi.NoteDef( midi.DRUM_PROGRAM, midi_number ) )
        self.set_virtual_drum_characteristics( dditem )
        
    def set_virtual_drum_characteristics(self, dditem ):
        # Define/redefine virtual drum characteristics
        # Called from at end of pinout definition, but also
        # from webserver.py to alter temporarily drum definitions
        # for testing
        self.drum_name = dditem["name"]
        # Store durations and the cluster of valves
        # to activate if a Simulated Drum note is played
        self.duration = dditem["duration"]
        # Calculate additional time for "stronger" notes in microseconds
        self.strong_added_time = max(0, dditem["strong_duration"] -  dditem["duration"])
        
        self.midi_virtual_pins = set() # of virtual_pins
        self.strong_midi_virtual_pins = set()
        for ddname, pinset in (("midi_list", self.midi_virtual_pins), ("strong_midis", self.strong_midi_virtual_pins) ):
            for midi_number in dditem[ddname]:
                pin = self._driver.actuator_bank.get_pin_by_midi_number( midi_number )
                if pin and pin.is_solepin:
                    pinset.add( pin )

        

    # Important restriction: cannot play two drum notes simultaneusly
    # They will play one after the other
    def on( self ):
        # Simulate a drum note without disturbing other notes that are be on
        # actuators_that_are_on() returns a list, must change to set.
        actuators_on = set(BasePin.get_active())
        virtual_pins = self.midi_virtual_pins - actuators_on
        strong_virtual_pins = self.strong_midi_virtual_pins - actuators_on
        # Use .low_level_on() and .low_level_off() it is faster but it does
        # not check polyphony.
        # Since driver_base._actuator_change() is NOT called below,
        # check here for polyphony. Instead of turning off old notes, steal
        # notes from the drum cluster.
        # Don't bother to update SolePin.sole_polyphony here, when
        # leaving this function, the drum note will be already turned off.
        allowed =  SolePin.config_max_polyphony - SolePin.sole_polyphony - len(strong_virtual_pins)
        if allowed <= 0:
            # Not enough power. It's not nice to turn off regular notes
            ActuatorStats.count( "ftom skipped")
            return
        while len(virtual_pins) >= allowed:
            virtual_pins.pop()
        

        # Sound all notes in the cluster
        for virtual_pin in strong_virtual_pins:
            virtual_pin.low_level_on()
        for virtual_pin in virtual_pins:
            virtual_pin.low_level_on()
        # Wait time is short (duration should be <= 50 milliseconds)
        # Don't use asyncio.sleep_ms because time will be not
        # controllable and the time is really too short to do other stuff
        # while waiting.
        # Duration of the drum note is the highest priority here.
        sleep_ms( self.duration )
        # Now turn off what has been turned on
        for virtual_pin in virtual_pins:
            virtual_pin.low_level_off()
        # Wait a bit to turn of stronger (accented) notes
        sleep_ms( self.strong_added_time )
        for virtual_pin in strong_virtual_pins:
            virtual_pin.low_level_off()
        BasePin._battery_consumption += (
            self.duration*len(virtual_pins) +
            (self.duration+self.strong_added_time)*len(strong_virtual_pins)
            )

    def off( self ):
        # Drum note has already been turned off in on() function
        return
    
    def __repr__( self ):
        return f"{self.drum_name}.{self.nominal_midi_number}"