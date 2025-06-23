# (c) 2023 Hermann Paul von Borries
# MIT License
# Solenoid note on/note off, hides difference between GPIO and MCP23027
# Uses MIDIdict to search efficently for the pin function given a MIDI Note

import machine
import asyncio
from time import sleep_ms
import minilog
from drehorgel import led
from midi import DRUM_PROGRAM

_logger = minilog.getLogger(__name__)

class ActuatorBank:
    # Holds all actuator drivers (and all actuators) according to
    # definition in pinout.json
    def __init__(self, max_polyphony, actuator_def ):

        # config_max_polyphony Controls maximum number of notes to sound simultaneously
        # so that the total current current doesn't exceed a limit.
        self.config_max_polyphony =  max( max_polyphony, 1)
        # This is the list of actuators that are currently
        # active. It is used to limit the number of actuators to
        # self.config_max_polyphony as a maximum. List elements are
        # actuators such as GPIOPin or MCP23017Pin or one MIDI serial actuator.
        self.active_actuators = []

        # Parsing fills these definitions:
        # pin_list: a list of all actuators that have been defined
        # in the pinout.
        self.pin_list = []
        # pin_info is info about MCP devices, to show to the user.
        self.pin_info = []

        self.sumsolenoid_on_msec = 0

        # Get the results from actuator_def
        self.pin_list = actuator_def.get_pin_list()
        self.driver_list = actuator_def.get_driver_list() 
        self.pin_info = actuator_def.get_pin_info()
        # Tell the drivers that here is the actuator bank

        for drv in self.driver_list:
            drv.set_actuator_bank( self )

        for pin in self.pin_list:
            pin.set_actuator_bank( self )

        self.pin_info = []
        for drv in self.driver_list:
            drv_repr = repr(drv)
            count = 0
            for pin in self.pin_list:
                if repr(pin).startswith(drv_repr + "."):
                    count += 1
            self.pin_info.append( (drv_repr,count) )
        _logger.debug(f"init complete {self.pin_info=}")

    def all_notes_off( self ):
        # All notes off is done at two levels.
        # Do it fast at driver level, to ensure all notes are off asap
        for drv in self.driver_list:
            drv.all_notes_off()

        # And reset at the actuator level too, not only driver level,
        # to ensure the actuator logic is synchronized with the driver level.
        for actuator in self.pin_list:
            actuator.force_off()
        self.active_actuators = []


    def add_active( self, actuator ):
        # Add actuator to self.active_actuators.
        # Check polyphony before adding another actuator.
        # Turn off oldest note until polyphony ok.
        while len(self.active_actuators) >= self.config_max_polyphony:
            # Blink led (don't wait blinking to be over)
            led.short_problem()
            # pop() should not raise IndexError since len(self.actuators) > 0
            # (self.config_max_polyphony is always >= 1 at least.
            self.active_actuators.pop(0).force_off()
        # Now we have capacity to add another actuator
        self.active_actuators.append( actuator )

    def remove_active( self, actuator ):
        # Remove actuator from list of active actuators.
        # If not present, ignore. This can happen with certain 
        # sequences of exceed polyphony and duplicate note off events.
        aa = self.active_actuators
        try:
            del aa[ aa.index( actuator )]
        except ValueError:
            pass
                 
    def add_operating_time( self, msec ):
        # Keep tally of time solenoids were on
        self.sumsolenoid_on_msec +=  msec      
        
    def get_sum_msec_solenoids_on_and_zero(self):
        t = self.sumsolenoid_on_msec
        self.sumsolenoid_on_msec = 0
        return t

    def get_status(self):
        # Get summary of current devices for display
        return self.pin_info

    def get_actuator_by_pin_index(self, pin_index):
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
    
    def get_pin_by_midi_number( self, midi_number ):
        # This is used during initalization only, it's not very important
        # for this code to be fast
        for pin in self.pin_list:
            m = pin.nominal_midi_note
            if (m.midi_number == midi_number and
                m.program_number != DRUM_PROGRAM ):
                return pin


    def actuators_that_are_on(self):
        # Return a list of actuators that are currently on
        # This is used by the driver_ftom to avoid using notes
        # that are already on.
        return self.active_actuators
    
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
        # Test a GPIO pin. Sometimes this does not work,
        # is random because of ambient electromagnetic noise.
        gp = machine.Pin(gpio_pin, machine.Pin.IN, machine.Pin.PULL_UP)
        with_pull_up = gp.value()
        gp = machine.Pin(gpio_pin, machine.Pin.IN, machine.Pin.PULL_DOWN)
        with_pull_down = gp.value()
        gp = machine.Pin(gpio_pin, machine.Pin.IN)
        # no_pull = gp.value()

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

    async def web_test_pin( self, pininfo ):
        # Called by web server to test a pin, expects a "pininfo" dict
        # with info filled out by pinout.html
        # The "pininfo" dictionary has all fields about the pin,
        # some fields may be superfluous.

        driver_type = pininfo["type"]

        # Compute a pinout repr to search for that pin.
        from driver_gpio import GPIODriver
        from driver_midiserial import MIDISerialDriver
        from driver_mcp23017 import MCP23017Driver
        from driver_gpioservo import GPIOServoDriver
        from driver_pca9685 import PCA9685Driver
        # These calls here must mirror the super().__init__() parameters in the
        # constructors of the respective classes:
        driver_dict = { 
            "gpio":      lambda: GPIODriver.make_repr() + str(pininfo['pin']),
            # Note that MIDISerial uses midi note number and NOT a "pin" number,
            # there is no "pin" for MIDISerial.
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
        from drehorgel import actuator_bank
        try:
            actuator = actuator_bank.get_pin_by_repr(pin_repr) 
        except KeyError:
             return f"Pin not found: {pin_repr}"

        for _ in range(8):
            actuator.value(1)
            await asyncio.sleep_ms(500)
            actuator.value(0)
            await asyncio.sleep_ms(500)

        