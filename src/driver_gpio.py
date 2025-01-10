# Copyright (c) 2023 Hermann von Borries
# MIT license

from machine import Pin

from driver_base import BasePin, BaseDriver

# This is called when a ["gpio"] definition is encountered
# in the current pinout.json to set up for MIDI definitions
# that go to GPIO pins on the ESP32-S3
class GPIODriver(BaseDriver):
    def __init__( self ):
        # Need a list of all pins for .all_notes_off() function
        self._gpiopins = []

    def define_pin( self, *args ):
        # Return a individual pin
        vp = GPIOPin( self, *args )
        # A pin could be twice in _gpiopins, but
        # since this is for all_notes_off, that does not matter
        self._gpiopins.append( vp )
        return vp

    def all_notes_off( self ):
        for gp in self._gpiopins:
            gp.value(0)
    
class GPIOPin(BasePin):
    def __init__( self,  driver, pin_number, rank, nominal_midi_note ):
        self._gpiopin = Pin( pin_number, Pin.OUT )
        super().__init__(driver, pin_number, rank, nominal_midi_note )

    def value( self, val):
        self._gpiopin.value(val)
