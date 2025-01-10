# (c) 2023 Hermann Paul von Borries
# MIT License
# Solenoid note on/note off, hides difference between GPIO and MCP23027
# Uses MIDIdict to search efficently for the pin function given a MIDI Note
from time import ticks_diff, ticks_ms, sleep_ms
import machine
import asyncio

import minilog
from drehorgel import led
from midi import DRUM_PROGRAM
from driver_null import NullPin


_logger = minilog.getLogger(__name__)

class ActuatorBank:
    # Holds all actuator drivers
    def __init__(self, max_polyphony, actuator_def ):

        # config_max_polyphony Controls maximum number of notes to sound simultaneously
        # so that the total current current doesn't exceed a limit.
        self.config_max_polyphony =  max_polyphony
        self.polyphony = 0

        # Parsing fills these definitions:
        # pin_list: a list of all actuators that have been defined
        # in the pinout.
        self.pin_list = []
        # device_info is info about MCP devices, to show to the user.
        self.device_info = {}

        self.sumsolenoid_on_msec = 0

        # Get the results from actuator_def
        self.pin_list = actuator_def.get_pin_list()
        self.driver_list = actuator_def.get_driver_list() 
        self.device_info = actuator_def.get_device_info()
        # Tell the drivers that here is the actuator bank
        for drv in self.driver_list:
            drv.set_actuator_bank( self )
        for pin in self.pin_list:
            pin.set_actuator_bank( self )

        _logger.debug(f"init complete {self.device_info=}")

    def all_notes_off( self ):
        for drv in self.driver_list:
            drv.all_notes_off()
        # Reset the counter of how many notes are on
        self.polyphony = 0

    def compute_polyphony( self, on_off ):
        # Increment/decrement polyphony counter.
        # Should never go below 0
        self.polyphony = max( self.polyphony + on_off, 0)
        
        if self.polyphony > self.config_max_polyphony:
            # Exceeding polyphony could lead to battery overload

            # Blink led
            led.short_problem()
            # This should be checked on a PC later

            # Turn off the oldest note. This code will
            # only act if maximum polyphony is exceeded
            now = ticks_ms()

            # The default value of max() should not happen, it is to prevent
            # a (very unlikely) ValueError
            oldest_time = max(
                (ticks_diff(p.on_time, now)
                for p in self.actuators_that_are_on()),
                default=-1 
            )
            # Turn off the oldest note(s)
            for actuator in self.pin_list:
                # Turn off all actuators that have been on the longest time
                if ticks_diff(actuator.on_time, now) >= oldest_time:
                    # This call to actuator.off() could make this method to
                    # recur if polyphony still exceeded.
                    actuator.off()
                    return
 
    def actuators_that_are_on( self ):
        return set( actuator for actuator in self.pin_list if actuator.on_time>=0 )

    def add_on_time( self, msec ):
        # Keep tally of time solenoids were on
        self.sumsolenoid_on_msec +=  msec      
        
    def get_sum_msec_solenoids_on_and_zero(self):
        t = self.sumsolenoid_on_msec
        self.sumsolenoid_on_msec = 0
        return t

    def get_status(self):
        # Get summary of current devices for display
        return self.device_info

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
        for pin in self.pin_list:
            m = pin.nominal_midi_note
            if (m.midi_number == midi_number and
                m.program_number != DRUM_PROGRAM ):
                return pin

    def get_driver_list( self ):
        return self.get_driver_list
    

# This module provides test functions WITHOUT
# need to define a pin. This enables to play with
# pin numbers on the pinout.html page and test them
# without saving the information before testing.
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

    # can be used here...
    # Used by web page to test one pin - physical chip level
    async def web_test_gpio(self, gpio_pin):
        gpio = machine.Pin(gpio_pin, machine.Pin.OUT)
        for _ in range(8):
            gpio.value(1)
            await asyncio.sleep_ms(500)
            gpio.value(0)
            await asyncio.sleep_ms(500)

    # Used by web page to test one pin of MCP23017 - physical chip level
    async def web_test_mcp(self, sda, scl, mcpaddr, mcp_pin):
        from driver_mcp23017 import MCP23017Driver
        from drehorgel import actuator_bank
        i2c = machine.SoftI2C(scl=machine.Pin(scl), sda=machine.Pin(sda))
        mcp = MCP23017Driver(i2c, 0, mcpaddr)
        pin = mcp.define_pin(mcp_pin, "", None )
        pin.set_actuator_bank( actuator_bank )
        pin.off()
        for _ in range(8):
            pin.on()
            await asyncio.sleep_ms(500)
            pin.off()
            await asyncio.sleep_ms(500)
