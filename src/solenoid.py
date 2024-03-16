# (c) 2023 Hermann Paul von Borries
# MIT License
# Solenoid note on/note off, hides difference between GPIO and MCP23027
# Uses MIDIdict to search efficently for the pin function given a MIDI Note
import asyncio
import time
import machine


from minilog import getLogger
import pinout
from config import config
import midi
from led import led

from mcp23017 import MCP23017

_logger = getLogger(__name__)


class simulated_MCP23017:
    def __init__(self):
        pass

    def __getitem__(self, p):
        return self

    def output(self, val=None):
        return val


# This is a singleton class to hold the definition for solenoid MIDI
class SolenoidPins(pinout.PinoutParser):
    def __init__(self):
        self.pin_functions = midi.MIDIdict()
        self.pin_names = midi.MIDIdict()
        self.device_info = {}

        self._current_i2c = None
        self._current_i2c_number = -1
        self._current_mcp23017 = None
        self._current_mcp_number = None
        # Start parsing with current definition
        super().__init__(None)

    def define_gpio_midi(self, gpio_pin, midi_note, rank):
        if not midi_note:
            return

        # Define function with closure to set/reset GPIO pins
        pin = machine.Pin(gpio_pin, machine.Pin.OUT)
        self.pin_functions[midi_note] = lambda v, gpiofun=pin.value: gpiofun(v)
        # Assign pin description
        self.pin_names[midi_note] = f"{rank} gpio.{gpio_pin}"

    def define_i2c(self, sda, scl):
        self._current_i2c_number += 1
        self._current_mcp_number = -1

        sclpin = machine.Pin(scl)
        sdapin = machine.Pin(sda)

        device_name = "i2c" + str(self._current_i2c_number)
        if pinout.test.testI2Cconnected(sda, scl) != (True, True):
            _logger.error(f"No I2C connected {sda=} {scl=}")
            self._current_i2c = None
            self.device_info[device_name] = "not connected"
        else:
            self._current_i2c = machine.SoftI2C(sclpin, sdapin, freq=100_000)
            self.device_info[device_name] = "ok"

    def define_mcp23017(self, address):
        self._current_mcp_number += 1
        mcpid = (
            "i2c"
            + str(self._current_i2c_number)
            + ".mcp."
            + str(self._current_mcp_number)
        )
        if address and self._current_i2c:
            _logger.debug(f"Try MCP23017 {self._current_i2c=} {address=}")
            try:
                self._current_mcp23017 = MCP23017(self._current_i2c, address)
                self.device_info[mcpid] = "ok"
            except OSError as e:
                _logger.exc(
                    e,
                    f"MCP23027 {mcpid} not found, disabled",
                )
                self.device_info[mcpid] = "ok"
                self._current_mcp23017 = simulated_MCP23017()
        else:
            self._current_mcp23017 = simulated_MCP23017()
            self.device_info[mcpid] = "test"

    def define_mcp_midi(self, mcp_pin, midi_note, rank):
        if not midi_note:
            return

        # Define function with closure to change value
        # of MCP23017 port
        self.pin_functions[midi_note] = lambda v, mpfun=self._current_mcp23017[
            mcp_pin
        ].output: mpfun(v)

        # Assign pin description
        self.pin_names[
            midi_note
        ] = f"{rank} mcp.{self._current_i2c_number}.{self._current_mcp_number}.{mcp_pin}"


class Solenoid:
    # Has all methods for solenoid valves to act according to midi notes played
    # Interprets Note On and Note Off  MIDI events
    def __init__(self, max_polyphony):
        # max_polyphony Controls maximum number of notes to sound simultaneously
        # so that the total current current doesn't exceed a limit.
        self.max_polyphony = max_polyphony

        # Parse pinout json to populate SolenoidDef
        self.init_pinout()
         
        self.sumsolenoid_on_msec = 0
        self.max_solenoids_on = 0

        self.all_notes_off()
        _logger.debug(f"init complete {self.solenoid_def.device_info=}")

    def all_notes_off(self):
        for midi_note in pinout.midinotes.get_all_valid_midis():
            self.note_off(midi_note)
        self.max_solenoids_on = 0

    async def play_random_note(self, duration_msec):
        midi_note = pinout.midinotes.get_random_midi_note()
        self.note_on(midi_note)
        await asyncio.sleep_ms(duration_msec)
        self.note_off(midi_note)

    async def clap(self, n, clap_interval_msec=50):
        _logger.debug(f"clap {n}")
        for _ in range(n):
            await self.play_random_note(clap_interval_msec)

    def note_on(self, midi_note):
        if midi_note not in self.solenoid_def.pin_functions:
            return
        # Turn note on
        self.solenoid_def.pin_functions[midi_note](1)

        # Record time of note on, note_off will compute time this solenoid was "on"
        now = time.ticks_ms()
        if self.solenoid_on_msec[midi_note] == 0:
            self.solenoid_on_msec[midi_note] = now
            # Compute how many notes are on
            # It's not a good idea to implement this with a counter only
            polyphony = sum(1 for x in self.solenoid_on_msec.values() if x != 0)
            if polyphony > self.max_polyphony:
                # This could lead to battery overload, record to log at end of tune
                self.max_solenoids_on = polyphony
                led.short_problem()
                # Turn off the oldest note
                oldest_time = min(
                    time.ticks_diff(x, now)
                    for x in self.solenoid_on_msec.values()
                    if x != 0
                )
                for k, v in self.solenoid_on_msec.items():
                    if v == oldest_time:
                        self.note_off(k)

    def note_off(self, midi_note):
        if midi_note not in self.solenoid_def.pin_functions:
            return
        # Turn note off
        self.solenoid_def.pin_functions[midi_note](0)
        # Compute time this note was on, add to battery use
        t0 = self.solenoid_on_msec[midi_note]
        # Ignore if note was never turned on
        if t0 != 0:
            self.sumsolenoid_on_msec += time.ticks_diff(time.ticks_ms(), t0)
        self.solenoid_on_msec[midi_note] = 0

    def get_sum_msec_solenoids_on_and_zero(self):
        t = self.sumsolenoid_on_msec
        self.sumsolenoid_on_msec = 0
        return t

    def get_status(self):
        # Get summary of current devices for display
        return self.solenoid_def.device_info

    def get_pin_name(self, midi_note):
        return self.solenoid_def.pin_names.get(midi_note, "")

    def init_pinout(self):
        # Called during initialization, and also from webserver when
        # changing pinout
        # Parse pinout json to define solenoid midi to pin
        self.solenoid_def = SolenoidPins()
        # Times a solenoid is on is computed as a basis
        # to calculate battery power consumed. That needs
        # to store the time when a note gets turned on.
        self.solenoid_on_msec = midi.MIDIdict()
        for m in pinout.midinotes.get_all_valid_midis():
            self.solenoid_on_msec[m] = 0
 

solenoid = Solenoid(config.cfg["max_polyphony"])
