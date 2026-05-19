# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# Manage ESP32-S3 GPIO pin definitions and port expander MCP23017 pin definitios
# and all other actuator definitions in the pinout files.

# This module parses the pinout files, e.g. 20_notes_Carl_Frei.json
# The parsed file is fed into several classes each of which 
# extracts an aspect of the information and organizes it,
# see below "subclasses of PinoutParser"

# >>> describe pinout.json file
# >>> up/down arrows are for servopulse and not midi note?
from machine import Pin, SoftI2C

from minilog import getLogger
from midi import NoteDef
import fileops
from midicontroller import MIDIController, RegisterBank
from solenoid import PinTest


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
# supported (not tested).
ESP32_S3_RESERVED_PINS  = [ 0, 19, 20,43, 44, 45, 46] +\
                          [ pin for pin in range(22,38) ]
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
#   class solenoids.ActuatorDef --> stores relationship
#       between
#       MIDI notes and actuator output pins on GPIO or MCP23017.
#   class pinout.GPIOstatistics --> provides information
#       about used, reserved and available GPIO pins of the ESP32-S3
#
#

_logger = getLogger( __name__ )

def get_current_pinout( pinout_txt_filename ):
    fn = None
    try:
        with open( pinout_txt_filename ) as file:
            fn = file.read()
    except:
        # Return None if not found.
        pass
    return fn

# superclass to parse pinout json file
class PinoutParser:
    def __init__(self, source, raise_error ):
        self.description = ""
        self.current_driver = "GPIODriver"

        # Receives either filename of the json file or
        # the list with the pinout data.
        self.raise_error = raise_error

        # Initialize all instance variables with defaults
        # in case parse() fails
        self.define_start()

        try:
            if isinstance(source, list):
                pinout_data = source
            elif isinstance(source, str):
                # source is a filename.
                pinout_data = fileops.read_json(source,
                            default=[],
                            recreate=True)
            else:
                # source is None, no pinout.txt found or empty
                _logger.error( "No current pinout file defined (no pinout.txt)")
                pinout_data = [] # A fallback to be able to continue and repair

            # Go through all "define" methods to gather info.
            self.parse(pinout_data)
        except Exception as e:
            _logger.exc( e, "Could not parse pinout json")
            if raise_error:
                raise
            
    def get_description(self):
        return self.description

    def toi(self, x):
        # Returns x converted to int, or None if x == ""
        if isinstance(x, int):
            return x
        # If not int, then x must be a string.
        if x.strip() == "":
            return None
        try:
            return int(x)
        except ValueError:
            raise RuntimeError(f"Integer expected: {x}")

    def parse(self, json_data):
        # Parses pinout json list, for each list element it
        # calls the corresponding method of the action object
        # MIDI notes are passed as NoteDef() object
        toi = self.toi
        actions = {
            "description": self.define_description,  # (description string)

            # GPIO pins for various devices
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
            # not in use anymore
            # "tempo": lambda pin_a, pin_b, switch: self.define_tempo( toi(pin_a), toi(pin_b), toi(switch) ),

            # MIDI driver definitions and "midi" pin definition
            "gpio": lambda : self.define_gpio_driver(),

            "i2c": lambda sda, scl: self.define_i2c(
                toi(sda), toi(scl)
            ),  # (sda, scl)
            "mcp23017": lambda addr: 
                self.define_mcp23017_driver( toi(addr) ),  # (address)
            "serial": lambda uart, pin, channel, rxpin: 
                        self.define_serial_driver( toi(uart), toi(pin), toi(channel), toi(rxpin)
            ),
            "gpioservo": lambda period_us: 
                          self.define_gpioservo_driver( toi(period_us) ),
            "pca9685": lambda addr, period_us:
                self.define_pca9685_driver( toi(addr), toi(period_us)),
            "servopulse": lambda pulse0_us, pulse1_us:
                self.define_servopulse( toi(pulse0_us), toi(pulse1_us) ),
            "midi": lambda pin,
            instrument,
            midi_num,
            rank,
            register="": self.define_midi(
                toi(pin), NoteDef(toi(instrument), toi(midi_num)), rank, register
            ),
        }
        self.define_start()
        for pd in json_data:
            # For transition from Oct24 version
            s = pd[0]
            if s.endswith(".midi"):
                s = "midi"
            # End of Oct24 transition
            try:
                actions[s](*pd[1:])
            except Exception as e:
                _logger.error(f"processing pinout file for line {pd} {e}, {'aborting' if self.raise_error else 'ignoring line'}")
                if self.raise_error:
                    raise
        self.define_complete()

    # To be overriden  by subclasses when neessary
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
    
    def define_i2c(self, sda, scl):
        return

    def define_gpio_driver( self ):
        self.current_driver = "GPIODriver"

    def define_mcp23017_driver(self, address):
        self.current_driver = "MCP23017Driver"

    def define_pca9685_driver(self, address, period_us):
        self.current_driver = "PCA9685Driver"

    def define_serial_driver( self, uart, pin, channel, rxpin ):
        self.current_driver = "MIDISerialDriver"

    def define_gpioservo_driver( self, period_us ):
        self.current_driver = "GPIOServoDriver"

    def define_servopulse( self, pulse0_us, pulse1_us ):
        pass
    
    def define_midi(self, pin, midi_note, rank, register_name):
        pass
    
    #def define_tempo( self, gpio_a, gpio_b, gpio_switch):
        # Not implemented
    #    return
        
    def define_complete(self):
        return


# Object to hold GPIO pin definitions and general pinout info
# except MIDI GPIOs.
# GPIO number 0 is always reserved, so for example
# "if not gpio.neopixel:" 
# means "no GPIO defined for neopixel"
class GPIODef(PinoutParser):
    def __init__(self, *args):
        self.register_bank = RegisterBank()
        global ESP32_S3_AVAILABLE_GPIO_PINS
        valid_pins = []
        for pin in ESP32_S3_AVAILABLE_GPIO_PINS:
            try:
                # Compare our definition to the MicroPython definition
                # Mark unavailable pins as reserved
                Pin( pin, Pin.IN )
                valid_pins.append( pin )
            except ValueError: # Invalid pin
                _logger.error( f"Pin {pin} is not available on this ESP32-S3")
                ESP32_S3_RESERVED_PINS.append( pin )
                del ESP32_S3_AVAILABLE_GPIO_PINS[ESP32_S3_AVAILABLE_GPIO_PINS.index(pin)]
        ESP32_S3_AVAILABLE_GPIO_PINS = valid_pins
        super().__init__(*args)

    def define_start( self ):
        # When using the result of GPIODef, these
        # instance variables can be read directly
        # to learn whether a certain device has been
        # defined.
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
            # Cache led number if not already
            from led import set_led
            set_led( x )

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

    #def define_tempo( self, gpio_a, gpio_b, gpio_switch):
    #    print(f"Not implemented: define tempo, ignored")
    
        # if gpio_a and gpio_b:
        #     self.tempo_a = gpio_a
        #     self.tempo_b = gpio_b
        #     self.tempo_switch = gpio_switch
            
    def define_register( self, gpio, name, initial_value ):
        # No name means "disregard this register"
        # Also: name cannot be blank, factory will return "always on"
        # register, and cannot set gpio pin for that...
        if name:
            # Make a new register or return one with this name
            reg = self.register_bank.factory( name )
            # If gpio is 0 or None or blank, no GPIO pin is set
            # and it's a software-only register
            # Check if this pin can be used
            reg.set_gpio_pin( gpio )
            # Set initial value at startup
            reg.set_initial_value(initial_value)
            # Nothing stored in this object

    def get_registers( self ):
        return self.register_bank 

class ActuatorDef(PinoutParser):
    # This class parses the pinout.json file to extract
    # the information about pins needed for the (valve) actuator driver
    # and also feeds the midi.Controller with information
    # about midi notes and their relation with driver_pin objects
    # Source: the filename of a pinout.json file or
    # a list object with the contents of the pinout.json file.
    # register_bank: the RegisterBank() object, already populated
    # with hardware register definitions (if any).
    def __init__(self, register_bank, *args):
        # We need the register bank to add defined registers
        self.register_bank = register_bank
        # Start with default value for pulse width; no movement
        # center position.
        self.pulse0_us = 1500
        self.pulse1_us = 1500
        # The result of the parse is:
        # pin_list/pin_dict: a the complete list of SolePin objects
        # These two will be accessed by Solenoid as a result of parsing pinout.json
        # Start parsing this pinout.json file
        super().__init__(*args)


    def driver_factory( self, newdriver ):
        # repr(driver) is unique. Create one of each kind
        # only.
        return self.driver_dict.setdefault( repr(newdriver), newdriver )


    def define_start( self ):
        self.pin_dict = {}
        self.driver_dict = {}
        self.known_programs = set() 
        self.known_programs.add(1) # 1 always is a known program...

        # Pass initialized registers to MIDIController
        self.controller = MIDIController( self.register_bank )

        self.current_i2c = None
        self.current_i2c_number = -1
        
        self.controller.define_start()

        # gpio driver is the default driver, should
        # the ["gpio"] entry in pinout.json be missing,
        # also for compatibility with previous versions
        from driver_gpio import GPIODriver
        self.current_driver = self.driver_factory( GPIODriver() )
        self.pin_list = []


    # define_register is defined in pinout.py/GPIOdef, not here  
    def define_i2c(self, sda, scl):
        self.current_i2c_number += 1

        sclpin = Pin(scl)
        sdapin = Pin(sda)

        if PinTest.testI2Cconnected(sda, scl):
            from drehorgel import config
            i2cfreq = config.i2c_frequency_khz 
            assert 10 <= i2cfreq <= 800, "I2C frequency must between 10 and 800 kHz"
            self.current_i2c = SoftI2C(sclpin, sdapin, freq=i2cfreq*1_000)
            # 100kHz = 2 msec per MCP23017 transaction (pin on or pin off)
            # 400kHz = 1 a 2 msec per MCP23017 transaction
            # About 25% faster. 
            _logger.info(f"Operating I2C {sda=} {scl=} at {i2cfreq} kHz")
        else:
            _logger.error(f"No I2C connected {sda=} {scl=}")
            self.current_i2c = None

    def define_mcp23017_driver(self, address):
        from driver_null import NullDriver
        # Default in case MCP23017 is not installed
        self.current_driver = self.driver_factory( NullDriver() )

        if self.current_i2c and address is not None :
            try:
                from driver_mcp23017 import MCP23017Driver

                self.current_driver = self.driver_factory( MCP23017Driver(self.current_i2c, self.current_i2c_number, address) )
            except OSError as e:
                _logger.error(
                    f"MCP23027 at {self.current_i2c=} {address=} disabled. {e}",
                )
                
    def define_pca9685_driver(self, address, period_us ):
        from driver_null import NullDriver
        # Default in case PCA9685 is not installed
        self.current_driver = self.driver_factory( NullDriver() )

        if self.current_i2c and address is not None :
            try:
                from driver_pca9685 import PCA9685Driver

                self.current_driver = self.driver_factory( PCA9685Driver(
                    self.current_i2c, self.current_i2c_number, address, period_us
                    ) )
            except OSError as e:
                _logger.error(
                    f"PCA9685 at {self.current_i2c=} {address=} disabled. {e}",
                )

    def define_gpio_driver( self ):
        from driver_gpio import GPIODriver
        self.current_driver = self.driver_factory( GPIODriver() )

    def define_gpioservo_driver( self, period_us ):
        from driver_gpioservo import GPIOServoDriver
        self.current_driver = self.driver_factory( GPIOServoDriver( period_us  ) )

    # >>> test if pinout can be ordered in different ways.
    def define_midi(self, pin, midi_note, rank, register_name ):
        # Disregard if midi_note.midi_number is None (i.e. blank in web page/pinout.json)
        # Also disregard if midi_note or program number out of range
        if not midi_note.is_correct():
            return
        # Get pin that is being defined
        pin = self.current_driver.define_pin( pin, rank, midi_note ) 
        # Servo pulse width is needed for RC servos, other pins will ignore this setting
        pin.set_servopulse( self.pulse0_us, self.pulse1_us )
        # Use repr() or str() to test for uniqueness,
        # for example: MCP23017Driver.I2C(0).3
        # If already defined, use previously defined pin
        # Using __hash__/__eq___ would need a dict anyhow, no way
        # to get element from set here.
        pin = self.pin_dict.setdefault( repr(pin), pin )
        # and pass this to the controller so MIDI can find the pin
        self.controller.define_note( midi_note, pin, register_name )

        p = midi_note.program_number
        if p: # don't wildcard to known programs
            self.known_programs.add( p )
        
    def define_serial_driver( self, uart, pin, channel, rxpin ):
        from driver_midiserial import MIDISerialDriver
        if not rxpin or not pin:
            from driver_null import NullDriver
            _logger.error("MIDI over serial tx pin and rx pin must be specified, edit pinout and add pin number")
            self.current_driver = self.driver_factory( NullDriver() )
            return
        self.current_driver = self.driver_factory( MIDISerialDriver( uart, pin, channel, rxpin ) )

    def define_servopulse( self, pulse0_us, pulse1_us ):
        # Save this for all following pins
        self.pulse0_us = pulse0_us
        self.pulse1_us = pulse1_us

    def define_complete( self ):
        self.pin_list = list( self.pin_dict.values() )
        # Organ tuner uses pin index (index to pin_list)
        # So for organ tuner it's nicer to sort by midi number
        # Also: for polyphony control, bass notes are turned off first 
        # (that's preferrable to turning off melody notes)
        # Sort pins by program number and midi note
        self.pin_list.sort( key=lambda pin:pin.nominal_midi_note.program_number*256+pin.nominal_midi_note.midi_number )

        # No need to delete structures like self.pin_dict here, the structures
        # actuator_def is transient and unneded structures will be freed anyhow.

    # Methods to return what's useful here
    # These are used by calling method to extract 
    # populated data structures/objects
    def get_pin_list( self ):
        return self.pin_list
    
    def get_controller( self ):
        return self.controller

    def get_driver_list( self ):
        return list(  self.driver_dict.values() )
