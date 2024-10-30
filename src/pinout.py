# (c) 2023 Hermann Paul von Borries
# MIT License
# Manage ESP32-S3 GPIO pin definitions and port expander MCP23017 pin definitios

# This module parses the pinout files, e.g. 20_notes_Carl_Frei.json
# The parsed file is fed into several classes each of which 
# extracts an aspect of the information and organizes it,
# see below "subclasses of PinoutParser"

import asyncio
import os
import machine
import time
import re

from mcp23017 import MCP23017

from config import config
import midi
import fileops
from midi import registers
# ESP32-S3 Technical Manual
# See 2.3.3 Restrictions for GPIOs and RTC_GPIOs
# See Table 2-3. IO MUX Pin Functions, 
# See Table 2-4. RTC and Analog Functions
# Reserved: 0 for bootstrapping, chip boot mode
# Usable: Pin 3 is JTAG signal source, ignored if eFuse 1, 2, 3 are zero.
# When GPIO0 and 3 are high on boot, device goes into bootloader.
# Reserved: 19, 20 for USB
# Reserved: 22 to 37 not usable, SPI, flash SPIRAM, not available
# Usable: 38 (is "neopixel" 3 color LED on some boards)
# Usable: 39 to 42: JTAG, unused if JTAG not enabled (enable with pin 3)
# Reserved: 43, 44: UART
# Reserved: 45, 46: VDD_SPI voltage, ROM message printing
# Please do not use the interrupt of GPIO36 and GPIO39 when using ADC or Wi-Fi and Bluetooth with sleep mode enabled.
# This definition is for ESP32-S3 N16R8 or N8R8.
# N32R8V has more reserved pins, but that should be
# taken into consideration below.
# No validation is done if used pin was a reserved pin.
ESP32_S3_RESERVED_PINS  = [ 0, 19, 20,43, 44, 45, 46] +\
                          [ pin for pin in range(22,38) ]
# ADC2 block cannot be used with WIFi
# Pins 1 to 10 are ADC1 pins
ESP32_S3_ADC1_PINS =  [ pin for pin in range(1,11) ]
# Pins 1 to 15 can be TouchPad pins
ESP32_S3_TOUCHPAD_PINS = [ pin for pin in range(1,15) ]
ESP32_S3_AVAILABLE_GPIO_PINS = [ pin for pin in range(49) if pin not in ESP32_S3_RESERVED_PINS]


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
#   class pinout.GPIODef --> stores pin definitions and MIDI notes
#   class pinout.SaveNewPinout --> Receives new json from web page
#       and saves to flash, but current definition is not
#       changed.
#   class solenoids.SolenoidDef --> stores relationship
#       between
#       MIDI notes and solenoid pins on GPIO or MCP23017.
#   class pinout.GPIOstatistics --> provides information
#       about used, reserved and available GPIO pins of the ESP32-S3
#
#
# Class PinTest:
#  provides low level functions to test pins,
#  called from webserver to serve test buttons on pinout page.
#  These functions are independent of the MIDI definitions.

logger = None
def get_minilog_lazy():
    global logger
    if not logger:
        from minilog import getLogger
        logger = getLogger( __name__ )

def logerror(message):
    get_minilog_lazy()
    logger.error(message)

def loginfo(message):
    get_minilog_lazy()
    logger.info(message)

# superclass to parse pinout json file
class PinoutParser:
    def __init__(self, source=None):
        # Receives eithe filename of the json file or
        # the list with the pinout data.
        # If source is None use current filename.
        source = source or plist.get_current_pinout_filename()
        if isinstance(source, list):
            pinout_data = source
        elif isinstance(source, str):
            pinout_data = fileops.read_json(source,
                        default=[],
                        recreate=True)
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
        # Returns x converted to int, or None if x == ""
        if isinstance(x, int):
            return x
        # To integer. "" is returned as "",
        # a integer string is returned as int
        x = x.strip()
        if x == "":
            return None
        try:
            return int(x)
        except ValueError:
            raise RuntimeError(f"Integer expected: {x}")

    def parse(self, json_data):
        # Parses pinout json list, for each list element it
        # calls the corresponding method of the action object
        # MIDI notes are passed as midi.NoteDef() object
        toi = self.toi
        actions = {
            "description": self.define_description,  # (description string)
            "neopixel": lambda pin: self.define_neopixel(
                toi(pin)
            ),  # (gpio number)
            # For transition: pin2 may absent on older versions of json file
            "tachometer": lambda pin1, pin2="": self.define_tachometer(
                toi(pin1),
                toi(pin2)
            ),  # (gpio number for counter or first encoder, gpio for encoder)
            "microphone": lambda pin: self.define_microphone(
                toi(pin)
            ),  # (gpio number)
            "touchpad": lambda pin: self.define_touchpad(
                toi(pin)
            ),  # (gpio number)
            "register": lambda pin, name, initial_value=False: self.define_register(
                toi(pin), name, initial_value
            ),
            "tempo": lambda pin_a, pin_b, switch: self.define_tempo( toi(pin_a), toi(pin_b), toi(switch) ),
            "gpio.midi": lambda pin,
            instrument,
            midi_num,
            rank,
            register=None: self.define_gpio_midi(
                toi(pin), midi.NoteDef(toi(instrument), toi(midi_num)), rank, register
            ),
            "i2c": lambda sda, scl: self.define_i2c(
                toi(sda), toi(scl)
            ),  # (sda, scl)
            "mcp23017": lambda addr: self.define_mcp23017(
                toi(addr)
            ),  # (address)
            "serial": lambda uart, pin, channel: self.define_serial( 
                toi(uart), toi(pin), toi(channel) 
            ),
            "mcp.midi": lambda pin,
            instrument,
            midi_num,
            rank,
            register=None: self.define_mcp_midi(
                toi(pin), midi.NoteDef(toi(instrument), toi(midi_num)), rank, register
            ),
            "serial.midi": lambda _,
            instrument,
            midi_num,
            rank,
            register=None: self.define_serial_midi(
                 midi.NoteDef(toi(instrument), toi(midi_num)), rank, register 
                 ),
        }

        self.define_start()
        try:
            for pd in json_data:
                actions[pd[0]](*pd[1:])
        except Exception as e:
            print("Exception processing pinout file for line", pd, e)
            raise
        self.define_complete()

    # All functions are empty except define_description.
    # To be filled out by subclasses
    def define_start( self ):
        return
    
    def define_description(self, x):
        # no need to override this method
        self.description = x

    def define_neopixel(self, gpio):
        return

    def define_tachometer(self, gpio1, gpio2):
        return

    def define_microphone(self, gpio):
        return

    def define_touchpad(self, gpio):
        return
    
    def define_register( self, gpio, name, initial_value ):
        return
    
    def define_gpio_midi(self, gpio_pin, midi_note, rank, register_name ):
        return

    def define_i2c(self, sda, scl):
        return

    def define_mcp23017(self, address):
        return

    def define_mcp_midi(self, mcp_pin, midi_note, rank, register_name):
        return
    
    def define_tempo( self, gpio_a, gpio_b, gpio_switch):
        return
    
    def define_serial( self, uart, pin, channel ):
        return
    
    def define_serial_midi( self, midi_note, rank, register_name ):
        return

    def define_complete(self):
        return


# Singleton object to hold GPIO pin definitions and general pinout info
# GPIO number 0 is always reserved, so  "if not gpio:" is used
# to mean "no GPIO defined here"
class GPIODef(PinoutParser):
    def __init__(self, source=None):
        super().__init__(source)

        global ESP32_S3_AVAILABLE_GPIO_PINS
        for pin in ESP32_S3_AVAILABLE_GPIO_PINS:
            try:
                # Compare our definition to the MicroPython definition
                # Mark unavailable pins as reserved
                machine.Pin( pin, machine.Pin.IN )
            except ValueError: # Invalid pin
                logerror( f"Pin {pin} is not available on this ESP32-S3")
                del ESP32_S3_AVAILABLE_GPIO_PINS[ESP32_S3_AVAILABLE_GPIO_PINS.index(pin)]
                ESP32_S3_RESERVED_PINS.append( pin )

    def define_start( self ):
        self.neopixel_pin = None
        self.tachometer_pin1 = None
        self.tachometer_pin2 = None
        self.microphone_pin = None
        self.touchpad_pin = None
        self.tempo_a = None
        self.tempo_b = None
        self.tempo_switch = None

    def define_neopixel(self, x):
        if x:
            self.neopixel_pin = x

    def define_tachometer(self, x1, x2):
        if x1:
            self.tachometer_pin1 = x1
        if x2:
            self.tachometer_pin2 = x2

    def define_microphone(self, x):
        if x:
            self.microphone_pin = x

    def define_touchpad(self, x):
        if x:
            self.touchpad_pin = x

    def define_tempo( self, gpio_a, gpio_b, gpio_switch):
        if gpio_a and gpio_b:
            self.tempo_a = gpio_a
            self.tempo_b = gpio_b
            self.tempo_switch = gpio_switch
            
    def define_register( self, gpio, name, initial_value ):
        reg = registers.factory( name )
        # If gpio is 0 or None or blank, no GPIO pin is set
        # and it's a software-only register
        try:
            # Check if this pin can be used
            reg.set_gpio_pin( gpio )
        except ValueError:
            logerror(f"Invalid pin {gpio}, cannot be used")
        # Set initial value at startup
        reg.set_initial_value(initial_value)
        # Nothing stored in this object

# Singleton class to validate a pinout and save it
# to the current json file. This class is invoked by
# the save button on pinout.html
# >>> check validations for duplicate gpio
# >>> no error message if json not valid?
class SaveNewPinout(PinoutParser):
    def __init__(self, source):
        # source must be json
        self.new_json = source
        # Validate data in memory
        super().__init__(source)

    def define_start( self ):
        self.gpiolist = []
        self.midilist = []
        self.mcplist = []
        self.mcp_port_list = []
        self.uart_list = []
        self.current_I2C = -1
        self.current_MCP_address = ""

    def _add_to_list(self, element, lst, message):
        if element:
            if element in lst:
                # Webserver checks and controls RuntimeError exceptions
                raise RuntimeError(message)
            lst.append(element)

    def _add_GPIO_to_list(self, gpio):
        if gpio:
            # Validate if pin can be used
            if gpio not in ESP32_S3_AVAILABLE_GPIO_PINS:
                raise RuntimeError(f"GPIO Pin {gpio} cannot be used")

            self._add_to_list(gpio, self.gpiolist, f"Duplicate GPIO {gpio}")
            
    def define_neopixel(self, gpio):
        self._add_GPIO_to_list(gpio)

    def define_tachometer(self, gpio1, gpio2 ):
        self._add_GPIO_to_list(gpio1)
        self._add_GPIO_to_list(gpio2)

    def define_microphone(self, gpio):
        if not gpio:
            return
        self._add_GPIO_to_list(gpio)
        if gpio not in ESP32_S3_ADC1_PINS:
            raise RuntimeError(f"Pin {gpio} must be ADC1 pin (3 to 10)")

    def define_touchpad(self, gpio):
        if not gpio:
            return
        self._add_GPIO_to_list(gpio)
        if gpio not in ESP32_S3_TOUCHPAD_PINS:
            raise RuntimeError(f"Pin {gpio} must be Touchpad pin (3 to 10)")

    def define_register( self, gpio, name, initial_value ):
        self._add_GPIO_to_list(gpio)

    def define_tempo( self, gpio_a, gpio_b, gpio_switch ):
        self._add_GPIO_to_list(gpio_a)
        self._add_GPIO_to_list(gpio_b)
        self._add_GPIO_to_list(gpio_switch)

    def define_gpio_midi(self, gpio_pin, midi_note, rank, register_name):
        if not gpio_pin:
            raise RuntimeError("GPIO pin blank or 0")
        # Check if used as gpio elsewhere (but don't check duplicate
        # use as gpio midi, because that's allowed)
        if gpio_pin in self.gpiolist:
            raise RuntimeError(f"MIDI GPIO pin already in use {gpio_pin}")
        if not midi_note.is_correct():
            raise RuntimeError("MIDI program or note number not in range")

        # GPIO pin can be used for more than one note
        # with different registers.

        # Same midi note can be in two or more places...


    def define_i2c(self, sda, scl):
        if not sda or not scl:
            raise RuntimeError("SDA or SCL pin blank or 0")
        self.current_I2C += 1
        self.current_MCP_address = ""
        self._add_GPIO_to_list(sda)
        self._add_GPIO_to_list(scl)

    def define_mcp23017(self, address):
        if address is None:
            raise RuntimeError("MCP address blank")
        self.current_MCP_address = address
        self._add_to_list(
            f"{self.current_I2C}.{address}",
            self.mcplist,
            f"Duplicate MCP, I2C {self.current_I2C} address {address}",
        )

    def define_mcp_midi(self, mcp_pin, midi_note, rank, register_name):
        if not( 0 <= mcp_pin <= 15 ):
            raise RuntimeError( "MCP pin number not 0-15")
        if mcp_pin is None:
            raise RuntimeError("MCP pin blank")
        if not midi_note.is_correct():
            raise RuntimeError("MIDI program or note number not in range")
    
    def define_serial( self, uart, pin, channel ):
        if not( 1<=uart<=2 ):
            raise RuntimeError("UART must be 1 or 2")
        if uart in self.uart_list:
            raise RuntimeError("Duplicate UART definition")
        if not( 0<=channel<=15):
            raise RuntimeError("Channel must be 0 to 15")
        self.uart_list.append( uart )
        self._add_GPIO_to_list(pin)
        # UART 1 by default uses also pin rx=9
        # UART 2 by default uses also pin rx=16
        # see https://docs.micropython.org/en/latest/esp32/quickref.html
        self._add_GPIO_to_list(9)
        self._add_GPIO_to_list(16)
        return
    
    def define_serial_midi( self, midi_note, rank, register_name ):
        if not midi_note.is_correct():
            raise RuntimeError("MIDI program or note number not in range")
        return

    def define_complete(self):
        self.gpiolist.sort()
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
            # No pinout files, can't work, fatal problem
            logerror("Error: no pinout files found in /data")

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
        # no pinout.txt, no pinout files???
        # Provide some basic default so nohting crashes
        fn = self.pinout_folder + "/1_note_minimal.json"
        with open( self.pinout_folder + "/pinout.txt", "w") as file:
            file.write(fn)
        with open( fn, "w" ) as file:
            file.write("[]")
        return fn


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
        for k in self.pinout_files.keys():
            self.pinout_files[k] = self.get_description(k)
        return list(self.pinout_files.items())

    def get_description(self, filename=None):
        if not filename:
            filename = self.current_pinout_filename
        if filename not in self.pinout_files:
            return f"file {filename} not found"
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

class GPIOstatistics(PinoutParser):
    def __init__( self ):
        # Get unique ocurrences
        self.used_gpio_pins = set()
        super().__init__()

    def _add_gpio( self, gpio ):
        if gpio != "" and gpio is not None:
            self.used_gpio_pins.add( gpio )  

    def define_neopixel(self, gpio):
        self._add_gpio( gpio )

    def define_tachometer(self, gpio1, gpio2 ):
        self._add_gpio( gpio1 )
        self._add_gpio( gpio2 )

    def define_microphone(self, gpio):
        self._add_gpio( gpio )

    def define_touchpad(self, gpio):
        self._add_gpio( gpio )
    
    def define_register( self, gpio, *args ):
        self._add_gpio( gpio )
    
    def define_gpio_midi(self, gpio, *args ):
        self._add_gpio( gpio )

    def define_i2c( self, sda, scl ):
        self._add_gpio( sda )
        self._add_gpio( scl )
 
    def define_tempo( self, gpio_a, gpio_b, gpio_switch ):
        self._add_gpio( gpio_a )
        self._add_gpio( gpio_b )
        self._add_gpio( gpio_switch )

    def get_used_pins( self ):
        # Sort GPIO pins
        gpiopins = [ x for x in self.used_gpio_pins ]
        gpiopins.sort()
        ESP32_S3_RESERVED_PINS.sort()
        availableGPIO = [ pin for pin in ESP32_S3_AVAILABLE_GPIO_PINS if pin not in gpiopins ]
        availableADC1 = [ pin for pin in ESP32_S3_ADC1_PINS if pin not in gpiopins ]
        availableTouchpad = [ pin for pin in ESP32_S3_TOUCHPAD_PINS if pin not in gpiopins ]
        return {
            "usedGPIO": gpiopins,
            "availableGPIO": availableGPIO,
            "reservedGPIO": ESP32_S3_RESERVED_PINS,
            "availableADC1": availableADC1,
            "availableTouchpad": availableTouchpad,
            "usedGPIOcount": len(gpiopins),
            "availableGPIOcount": len(availableGPIO),
            "reservedGPIOcount": len(ESP32_S3_RESERVED_PINS),
            "availableADC1count": len(availableADC1),
            "availableTouchpadcount": len(availableTouchpad)
        }

plist = None
gpio = None
test = None


def _init():
    global plist, gpio, test
    plist = PinoutList(config.PINOUT_TXT, config.PINOUT_FOLDER)
    gpio = GPIODef()
    test = PinTest()


_init()
