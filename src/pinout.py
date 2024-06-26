# (c) 2023 Hermann Paul von Borries
# MIT License
# Manage ESP32-S3 GPIO pin definitions and port expander MCP23017 pin definitios

import asyncio
import os
import machine
import time
from random import randrange
import re

from mcp23017 import MCP23017

from config import config
import midi
import fileops

# ClassPinoutList
#   manages list of possible pinouts files and holds
#   filename of current json file.
#   Pinout files must have the filename of the format
#   <number>_note_<description>.json
#   Where <number> is the number of notes and
#   <description> the name, example:
#   20_note_Carl_Frei.json
#   has <number> equal to 20 and <description> equal
#   to Carl_Frei
#
# PinoutParser: provides parsing of pinout json files.
# Subclasses of PinoutParser implement specific parsers:
#   class pinout.GPIO_MIDI --> stores pin definitions and MIDI notes
#   class pinout.SaveNewPinout --> Receives new json from web page
#       and saves to flash, but current definition is not
#       changed.
#   class solenoid.SolenoidPins --> stores relationship
#       between
#       MIDI notes and solenoid pins on GPIO or MCP23017.
#
# Class PinTest:
#  provides low level functions to test pins,
#  called from webserver to serve test buttons on pinout page.
#  These functions are independent of the MIDI definitions.


# superclass to parse pinout json file
class PinoutParser:
    def __init__(self, source=None):
        # Receives eithe filename of the json file or
        # the list with the pinout data.
        if source is None:
            source = plist.get_current_pinout_filename()
        if isinstance(source, list):
            pinout_data = source
        elif isinstance(source, str):
            pinout_data = fileops.read_json(source)
        else:
            raise RuntimeError(
                "PinoutParser neither filename nor list received, no pinout files in /data"
            )
        self.description = ""
        self.parse(pinout_data)

    def get_filename(self):
        return self.filename

    def get_description(self):
        return self.description

    def toi(self, x):
        if isinstance(x, int):
            return x
        # To integer. "" is returned as "",
        # a integer string is returned as int
        x = x.strip()
        if x == "":
            return ""
        try:
            return int(x)
        except ValueError:
            raise RuntimeError(f"Integer expected: {x}")

    def parse(self, json_data):
        # Parses pinout json list, for each list element it
        # calls the corresponding method of the action object
        # MIDI notes are passed as midi.Note() object
        toi = self.toi
        actions = {
            "description": self.define_description,  # (description string)
            "neopixel": lambda pin: self.define_neopixel(
                toi(pin)
            ),  # (gpio number)
            "tachometer": lambda pin: self.define_tachometer(
                toi(pin)
            ),  # (gpio number)
            "microphone": lambda pin: self.define_microphone(
                toi(pin)
            ),  # (gpio number)
            "touchpad": lambda pin: self.define_touchpad(
                toi(pin)
            ),  # (gpio number)
            "gpio.midi": lambda pin,
            instrument,
            midi_num,
            rank: self.define_gpio_midi(
                toi(pin), midi.Note(toi(instrument), toi(midi_num)), rank
            ),
            "i2c": lambda sda, scl: self.define_i2c(
                toi(sda), toi(scl)
            ),  # (sda, scl)
            "mcp23017": lambda addr: self.define_mcp23017(
                toi(addr)
            ),  # (address)
            "mcp.midi": lambda pin,
            instrument,
            midi_num,
            rank: self.define_mcp_midi(
                toi(pin), midi.Note(toi(instrument), toi(midi_num)), rank
            ),
        }
        for pd in json_data:
            actions[pd[0]](*pd[1:])

        self.parse_complete()

    # All functions are empty except define_description.
    # To be filled out by subclasses

    def define_description(self, x):
        # no need to override this method
        self.description = x

    def define_neopixel(self, gpio):
        return

    def define_tachometer(self, gpio):
        return

    def define_microphone(self, gpio):
        return

    def define_touchpad(self, gpio):
        return

    def define_gpio_midi(self, gpio_pin, midi_note, rank):
        return

    def define_i2c(self, sda, scl):
        return

    def define_mcp23017(self, address):
        return

    def define_mcp_midi(self, mcp_pin, midi_note, rank):
        return

    def parse_complete(self):
        return


# Singleton object to hold GPIO pin definitions and general pinout info
class GPIO_MIDI(PinoutParser):
    def __init__(self, source=None):
        self.neopixel_pin = None
        self.tachometer_pin = None
        self.microphone_pin = None
        self.touchpad_pin = None
        self.all_valid_midis = []
        super().__init__(source)

    def define_neopixel(self, x):
        if x:
            self.neopixel_pin = x

    def define_tachometer(self, x):
        if x:
            self.tachometer_pin = x

    def define_microphone(self, x):
        if x:
            self.microphone_pin = x

    def define_touchpad(self, x):
        if x:
            self.touchpad_pin = x

    # Include for completeness, when using this class as template:
    def define_gpio_midi(self, gpio_pin, midi_note, rank):
        if midi_note:
            self.all_valid_midis.append(midi_note)

    def define_mcp_midi(self, mcp_pin, midi_note, rank):
        if midi_note:
            self.all_valid_midis.append(midi_note)

    def parse_complete(self):
        self.all_valid_midis.sort(key=lambda m: m.hash)

    def get_all_valid_midis(self):
        # New function
        return self.all_valid_midis

    # Get a random note of all_valid_midis
    def get_random_midi_note(self):
        return self.all_valid_midis[randrange(0, len(self.all_valid_midis))]


# Singleton class to validate a pinout and save it
# to the current jaon file
class SaveNewPinout(PinoutParser):
    def __init__(self, source):
        self.gpiolist = []
        self.midilist = []
        self.mcplist = []
        self.mcp_port_list = []
        self.current_I2C = -1
        self.current_MCP_address = ""
        # source must be json
        self.new_json = source
        # Validate data in memory
        super().__init__(source)

    def _add_to_list(self, element, lst, message):
        if not element:
            return
        if element in lst:
            # Webserver checks and controls RuntimeError exceptions
            raise RuntimeError(message)
        lst.append(element)

    def _add_GPIO_to_list(self, gpio):
        self._add_to_list(gpio, self.gpiolist, f"Duplicate GPIO {gpio}")

    def _add_MIDI_to_list(self, midi_note):
        self._add_to_list(
            midi_note, self.midilist, f"Duplicate MIDI note {midi_note}"
        )

    def define_neopixel(self, gpio):
        self._add_GPIO_to_list(gpio)

    def define_tachometer(self, gpio):
        self._add_GPIO_to_list(gpio)

    def define_microphone(self, gpio):
        self._add_GPIO_to_list(gpio)

    def define_touchpad(self, gpio):
        self._add_GPIO_to_list(gpio)

    def define_gpio_midi(self, gpio_pin, midi_note, rank):
        self._add_GPIO_to_list(gpio_pin)
        self._add_MIDI_to_list(midi_note)

    def define_i2c(self, sda, scl):
        self.current_I2C += 1
        self.current_MCP_address = ""
        self._add_GPIO_to_list(sda)
        self._add_GPIO_to_list(scl)

    def define_mcp23017(self, address):
        self.current_MCP_address = address
        self._add_to_list(
            f"{self.current_I2C}.{address}",
            self.mcplist,
            f"Duplicate MCP, I2C {self.current_I2C} address {address}",
        )

    def define_mcp_midi(self, mcp_pin, midi_note, rank):
        self._add_MIDI_to_list(midi_note)
        mp = f"{self.current_I2C}.{self.current_MCP_address}.{mcp_pin}"
        self._add_to_list(
            mp,
            self.mcp_port_list,
            f"Duplicate MIDI port I2C.MCPaddress.port={mp}",
        )

    def parse_complete(self):
        # Replace current pinout filenam
        filename = plist.get_current_pinout_filename()
        fileops.write_json(self.new_json, filename)
        # Load json again
        # Webserver will inform solenoid and organtuner
        _init()


class PinoutList:
    def __init__(self, pinout_txt_filename, pinout_folder):
        self.pinout_txt_filename = pinout_txt_filename
        self.pinout_folder = pinout_folder

        # self.pinout_files is a dict, key=filename, data=description
        self._fill_pinout_files()

        self.current_pinout_filename = self._read_pinout_txt()

    def _fill_pinout_files(self):
        # Pinout files have to be in the data folder,
        # have type json and have "_note_" in the file name.
        # and start with a digit 1 to 9.
        # Examples: 20_note_Carl_Freil.json, 31_note_Raffin.json)
        # self.pinout_files is a dict, key=filename, value=description (initally blank, filled later)
        self.pinout_files = {}
        pattern = re.compile("^[0-9]+_note_.+\.json$")
        for fn in os.listdir(self.pinout_folder):
            # Pinout files must have the form <nnn>_note_<name>.json
            # where <nnn> is the number of notes of the scale and
            # <name> is the name itself, example 20_note_Carl_Frei.json
            # where 20 is the number of notes and Carl_Frei is the name.
            if re.match(pattern, fn):
                filename = self.pinout_folder + "/" + fn
                # the value is the description, get that
                # only when needed
                self.pinout_files[filename] = ""

        if len(self.pinout_files) == 0:
            print("Error: no pinout files found in /data")

    def _read_pinout_txt(self):
        # Better separate file than config.json. That
        # way led pin can be read before reading config.
        try:
            with open(self.pinout_txt_filename) as file:
                # Return filename of nn_xxxxx.json with pinout info
                return file.read()
        except OSError:
            # Return first available filename
            for k in self.pinout_files.keys():
                return k

    def set_current_pinout_filename(self, new_pinout_filename):
        if new_pinout_filename not in self.pinout_files:
            raise ValueError(f"Invalid pinout file {new_pinout_filename}")
        fileops.backup(self.pinout_txt_filename)
        with open(self.pinout_txt_filename, "w") as file:
            file.write(new_pinout_filename)
        # Must parse all instances again to take effect
        _init()
        # Webserver reinitializes solenoid

    def get_current_pinout_filename(self):
        return self.current_pinout_filename

    def get_filenames_descriptions(self):
        # Return list of pairs ( filename, description )
        # Fill descriptions on demand to make initialization
        # faster
        for k, v in self.pinout_files.items():
            self.pinout_files[k] = self.get_description(k)
        return list(self.pinout_files.items())

    def get_description(self, filename=None):
        if not filename:
            filename = self.current_pinout_filename
        # Is the description already there? If not, get it now
        if self.pinout_files[filename] == "":
            # Parse json to get description only
            self.pinout_files[filename] = PinoutParser(
                filename
            ).get_description()
        return self.pinout_files[filename]


# ========================
# Test functions
# ========================
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
            time.sleep_ms(1)
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
        return (sdaok, sclok)

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
        i2c = machine.SoftI2C(scl=machine.Pin(scl), sda=machine.Pin(sda))
        mcp = MCP23017(i2c, mcpaddr)
        mcp[mcp_pin].output()
        for _ in range(8):
            mcp[mcp_pin].output(1)
            await asyncio.sleep_ms(500)
            mcp[mcp_pin].output(0)
            await asyncio.sleep_ms(500)


plist = None
gpio = None
midinotes = None
test = None


def _init():
    global plist, gpio, midinotes, test
    plist = PinoutList(config.PINOUT_TXT, config.PINOUT_FOLDER)
    gpio = GPIO_MIDI()
    # midinotes is just another name for gpio
    midinotes = gpio
    test = PinTest()


_init()
