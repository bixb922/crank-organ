# Copyright (c) 2023 Hermann von Borries
# MIT license

import time

import fileops
from drehorgel import config
import midi
from driver_base import BaseDriver, BasePin, singleton

@singleton
class FauxTomDriver(BaseDriver):
    def __init__( self ):
        temp_def = fileops.read_json( config.DRUMDEF_JSON, default={})
        # Need the midi numbers used as key be an int
        self.drum_def = { int(m): temp_def[m] for m in temp_def }
        self.pin_list = []

    def save( self, new_drumdef ):
        # >>> perhaps we should validate correct contents??
        fileops.write_json( config.DRUMDEF_JSON, new_drumdef )
    
    # Provide iterator for all defined drums
    # This is different from other drivers, where
    # the midi notes are defined in the pinout.json whereas
    # here they are defined in drumdef.json
    def __iter__( self ):
        self.iter_drums = iter(self.drum_def.keys())
        return self
    
    def __next__( self ):
        # Return a new VirtualDrumPin() object for each iteration
        midi_number = next( self.iter_drums )
        dd = self.drum_def[midi_number]
        vdp = VirtualDrumPin( self, midi_number, dd, self._actuator_bank )
        self.pin_list.append( vdp )
        return vdp
    
    def get_pin_list( self ):
        return self.pin_list

# Virtual drum pin, virtual because it's not a hardware pin
# and pin because it must have the BasePin interface
class VirtualDrumPin(BasePin):
    # Must have same interface as driver pins (except __init__)
    # which is called by FauxTomDriver
    # (but BaseDriver is not the base class for this class)
    def __init__( self, driver, midi_number, drumdef, actuator_bank ):
        super().__init__( driver, midi_number, "Simulated drum", midi.NoteDef( midi.DRUM_PROGRAM, midi_number ) )
        self.driver = driver
        self.actuator_bank = actuator_bank
        self.set_virtual_drum_characteristics( drumdef )
        
    def set_virtual_drum_characteristics(self, drumdef ):
        # Define/redefine virtual drum characteristics
        # Called from at end of pinout definition, but also
        # from webserver.py to alter temporarily drum definitions
        # for testing
        self.drum_name = drumdef["name"]
        # Store durations and the cluster of valves
        # to activate if a Simulated Drum note is played
        # Durations to microseconds because time.sleep_ms
        # is not very precise on the ESP32.
        self.duration = drumdef["duration"]*1000
        # Calculate additional time for "stronger" notes in microseconds
        self.strong_added_time =  (drumdef["strong_duration"] -  drumdef["duration"])*1000
        
        self.midi_virtual_pins = set() # of virtual_pins
        for midi_number in drumdef["midi_list"]:
            pin = self.actuator_bank.get_pin_by_midi_number( midi_number )
            if pin:
                self.midi_virtual_pins.add( pin )
        self.strong_midi_virtual_pins = set()
        for midi_number in drumdef["strong_midis"]:
            pin = self.actuator_bank.get_pin_by_midi_number( midi_number )
            if pin:
                self.strong_midi_virtual_pins.add( pin )
        # >>> this is probably shorter
        #self.strong_midi_virtual_pins = { pin for pin in
        #    ( self.actuator_bank.get_pin_by_midi_number(m) for m in drumdef["strong_midis"])
        #     if pin }
    # Important restriction: cannot play two drum notes simultaneusly
    # They will play one after the other
    def on( self ):
        # Simulate a drum note without disturbing other notes that are be on
        actuators_on = self.actuator_bank.actuators_that_are_on()
        virtual_pin_list = self.midi_virtual_pins - actuators_on
        strong_virtual_pin_list = self.strong_midi_virtual_pins - actuators_on
        # Sound all notes in the cluster
        for virtual_pin in strong_virtual_pin_list:
            virtual_pin.on()
        for virtual_pin in virtual_pin_list:
            virtual_pin.on()
        # Wait here with time.sleep_us() to control the timing well.
        # Wait time is short (duration should be <= 50 milliseconds)
        # Don't use asyncio.sleep_ms because time will be not
        # controllable and the time is really too short to do other stuff
        # while waiting
        # Duration of the drum note is the highest priority here.
        time.sleep_us( self.duration )

        # Now turn this off
        for virtual_pin in virtual_pin_list:
            virtual_pin.off()
        # Wait a bit to turn of stronger (accented) notes
        time.sleep_us( self.strong_added_time )
        for virtual_pin in strong_virtual_pin_list:
            virtual_pin.off()


    def off( self ):
        # Drum note has already been turned off in on() function
        return
    
    def __repr__( self ):
        return f"{self.drum_name}.{self.nominal_midi_number}"