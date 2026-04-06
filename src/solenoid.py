# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
# Solenoid note on/note off, hides difference between GPIO and MCP23027
# Uses MIDIdict to search efficently for the pin function given a MIDI Note

import machine
import asyncio
from time import sleep_ms
import minilog
from drehorgel import led
from midi import DRUM_PROGRAM
from driver_base import RCServoPin, BasePin, SolePin

_logger = minilog.getLogger(__name__)


class ActuatorBank:
    # Holds all actuator drivers (and all actuators) according to
    # definition in pinout.json
    def __init__(self, actuator_def,  config ):
        # Parsing fills these definitions.
        # pin_list: a list of all actuators that have been defined
        # in the pinout.
        # pin_info is info about all devices, to show to the user.
        self.pin_list = actuator_def.get_pin_list()
        self.driver_list = actuator_def.get_driver_list() 
        self.known_programs = actuator_def.known_programs

        # Inject configuration for pins
        RCServoPin.set_config( config )
        SolePin.set_config( config )
        BasePin.set_led( led )
        BasePin.set_pinlist( self.pin_list )


        # Gather some info for diag.html
        pi = self.get_pin_info(", ")
        _logger.debug(f"init complete {pi}")

    def all_notes_off( self ):
        # Don't flash led if some problem occurs during all notes off,
        # It's distracting
        BasePin.set_led( None )

        # Some drivers have a very fast and
        # very effective "all notes off" 
        # method, for example MIDI output and MCP23017.
        # pin objects are not informed about this change,
        # so below we turn off all pins anyhow.
        for drv in self.driver_list:
            if hasattr( drv, "all_notes_off"):
                drv.all_notes_off()

        # Use force_off() to ensure that
        # mismatched note on/note off pairs are turned off,
        # and to leave pins in a consistent state.
        for actuator in self.pin_list:
            actuator.force_off()

        # Reset state now that all notes are off
        SolePin.clear_active()
        
        BasePin.set_led( led )

    def get_pin_info(self, sep):
        # Get summary of current devices for display
        pin_info = []
        for drv in self.driver_list:
            drv_repr = repr(drv)+"."
            pin_info.append( 
                (drv_repr[:-1], 
                sum( 1 for pin in self.pin_list if repr(pin).startswith(drv_repr))) )
        return sep.join(f"{drv} {pins} pins" for drv, pins in pin_info)

    def get_actuator_by_pin_index(self, pin_index):
        # organtuner.py refers to a pin with it's index
        # in the pin_list. Since the organtuner's pin_index
        # is derived from the pin_list, this works, since
        # solenoids.py and organtuner.py are based on self.pin_list.
        # Also, organtuner.json synchronizes with self.pin_list
        # at each reboot.
        return self.pin_list[pin_index]
    
    def get_all_pins( self ):
        # Used by organtuner.py to populate organtuner.json
        return self.pin_list

    def get_pin_count( self ):
        return len( self.pin_list )
    
    def get_pin_by_midi_number( self, midi_number ):
        # This is used during initalization of Faux Toms only, it's not very important
        # for this code to be fast
        for pin in self.pin_list:
            m = pin.nominal_midi_note
            if (m.midi_number == midi_number and
                m.program_number != DRUM_PROGRAM ):
                return pin
        # Return None if not found
    
    def get_pin_by_repr( self, name ):
        # We could keep pin_dict to make this faster
        # but it is fast enough as it is.
        for pin in self.pin_list:
            if repr(pin) == name:
                return pin
        raise KeyError
    
# This module provides test functions at pin level.
#
# There is also the testi2cconnected() function that
# can detect if NO I2C IS CONNECTED to a pair of pins.
# However, if it says "I2C connected", there is still
# a probability this is not true. But if it says "not connected",
# then there is no I2C device on these pins.
class PinTest:
 
    def _basicTestGPIO(self, gpio_pin):
        # Test if a GPIO pin has some kind of load
        # i.e. something connected
        gp = machine.Pin(gpio_pin, machine.Pin.IN, machine.Pin.PULL_UP)
        with_pull_up = gp.value()
        gp = machine.Pin(gpio_pin, machine.Pin.IN, machine.Pin.PULL_DOWN)
        with_pull_down = gp.value()
        gp = machine.Pin(gpio_pin, machine.Pin.IN)

        n = with_pull_up * 2 + with_pull_down
        # 00 = something pulls down for all cases. Might be a ULN2803 or
        # some other device.
        # 01 = ??? probably not connected
        # 10 = input follows the pull ups, not connected
        # 11 = there is something that pulls up this pin, example: I2C
        return ("DEV", "???", "NC", "I2C")[n]

    # Test several times if something pulls the voltage
    # up or down on the pin
    def _testGPIO(self, pin, repeat=10):
        res = set()
        for _ in range(repeat):
            sleep_ms(1)
            r = self._basicTestGPIO(pin)
            res.add(r)
        if len(res) == 1:
            return res.pop()
        else:
            return "FLO"

    # Used by solenoid.py to check if something on I2C
    def testI2Cconnected(self, sda, scl):
        sdaok = self._testGPIO(sda) == "I2C"
        sclok = self._testGPIO(scl) == "I2C"
        return sdaok and sclok

    async def web_test_pin( self, pininfo, actuator_bank ):
        # Called by web server to test a pin, expects a "pininfo" dict
        # with info filled out by pinout.html
        # The "pininfo" dictionary has all fields about the pin,
        # some fields may be superfluous.
        
        _logger.debug(f"Web test pin {pininfo=}")
        driver_type = pininfo["type"]

        # Compute a pinout repr to search for that pin.
        from driver_gpio import GPIODriver
        from driver_midiserial import MIDISerialDriver
        from driver_mcp23017 import MCP23017Driver
        from driver_gpioservo import GPIOServoDriver
        from driver_pca9685 import PCA9685Driver
        # These calls here must mirror the super().__init__() parameters in the
        # constructors of their respective classes:
        driver_dict = { 
            "gpio":      lambda: GPIODriver.make_repr() + "." + str(pininfo['pin']),
            # Note that MIDISerial uses midi note number and NOT a "pin" number,
            # there is no "pin" for MIDISerial but "midi".
            "serial":   lambda: MIDISerialDriver.make_repr(pininfo['uart']) + "." + str(pininfo['midi']),
            "mcp23017": lambda: MCP23017Driver.make_repr(pininfo['i2ccount'],pininfo['mcpaddr']) + "." + str(pininfo['pin']),
            "gpioservo": lambda: GPIOServoDriver.make_repr() + "." + str(pininfo['pin']),
            "pca9685":   lambda: PCA9685Driver.make_repr(pininfo['i2ccount'],pininfo['pcaaddr']) + "." + str(pininfo['pin'])
        }    
        try:
            pin_repr = driver_dict[driver_type]()
        except:
            return f"Unknown driver: {driver_type}"
        # Now get the actuator for that pin.
        try:
            actuator = actuator_bank.get_pin_by_repr(pin_repr) 
        except KeyError:
             return f"Pin not found: {pin_repr}"

        try:
            # Non RC Servo pins will ignore this call
            actuator.set_servopulse( int(pininfo["pulse0"]), int(pininfo["pulse1"]))
        except (KeyError, AttributeError):
            # No pulse0/pulse1 info in pininfo, ignore.
            # Or actuator does not support set_servopulse, ignore.
            pass
        
        # No worries about polyphony or moving servos here
        # since there is not much else happening.
        # So we use low level functions that don't check current consumption limits.
        for _ in range(pininfo["repeat"]):
            actuator.low_level_on()
            await asyncio.sleep_ms(pininfo["pause"])
            actuator.low_level_off()
            await asyncio.sleep_ms(pininfo["pause"])

        # If pininfo["repeat"] is 0, 
        # then reset off position anyhow. 
        # This makes it easy to adjust
        # "off" position of each servo with arrow buttons
        await asyncio.sleep_ms(120)
        actuator.low_level_off()
        # RC Servo low_level_off will eventually call stop_pwm()