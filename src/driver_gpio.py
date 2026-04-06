# Copyright (c) 2023-2025 Hermann von Borries
# MIT license

from machine import Pin

from driver_base import SolePin, BaseDriver

# This is called when a ["gpio"] definition is encountered
# in the current pinout.json to set up for MIDI definitions
# that go to GPIO pins on the ESP32-S3.
# There is only one GPIODriver for all GPIO pins

# Does not need to be declared @singleton. Since __repr__ is
# defined in BaseDriver, GPIODriver has only one instance, see ActuatorDef.driver_factory()
class GPIODriver(BaseDriver):

    def define_pin( self, *args ):
        # Return a individual pin
        return GPIOPin( self, *args )

class GPIOPin(SolePin):
    def __init__( self,  driver, pin_number, rank, nominal_midi_note ):
        self._gpiopin = Pin( pin_number, Pin.OUT )
        super().__init__(driver, pin_number, rank, nominal_midi_note )

    def low_level_on( self ):
        self._gpiopin.value(1)

    def low_level_off( self ):
        self._gpiopin.value(0)
