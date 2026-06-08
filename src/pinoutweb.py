import os
import re

import fileops
from minilog import getLogger

# Reserved and available pins are updated by GPIODef at startup
# and are validated against MicroPython's board definition.
from pinout import PinoutParser, ESP32_S3_RESERVED_PINS, ESP32_S3_AVAILABLE_GPIO_PINS, get_current_pinout

# Pins 1 to 10 can be ADC1 pins, ADC2 block cannot be used with WiFi 
_ESP32_S3_ADC1_PINS = const((1,2,3,4,5,6,7,8,10)) # [ pin for pin in range(1,11) 

# Pins 1 to 15 can be TouchPad pins
_ESP32_S3_TOUCHPAD_PINS = const((1,2,3,4,5,6,7,8,9,10,11,12,13,14)) # [ pin for pin in range(1,15) ]

# Class to validate a pinout and save it
# to the current json file. This class is invoked by
# the save button on pinout.html
# These checks are not applied when loading the pinout,
# so if the pinout.json is modified externally, it's a good idea
# to save it once to check it.
class SaveNewPinout(PinoutParser):
    def __init__(self, output_filename, source, raise_error):
        # source must be json formatted list
        self.new_json = source
        self.output_filename = output_filename
        # Validate data in memory
        super().__init__(source, raise_error)
        self.current_driver = None
        
    def define_start( self ):
        self.gpiolist = []
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
        if gpio not in _ESP32_S3_ADC1_PINS:
            raise RuntimeError(f"Pin {gpio} must be ADC1 pin (3 to 10)")

    # For "touchpad" entry
    def define_touchpad( self, gpio, technology ):
        if not gpio:
            # Not assigned, ignore
            return
        from touchpad import validate_technology
        validate_technology( technology )
        self._add_GPIO_to_list(gpio)
        if gpio not in _ESP32_S3_TOUCHPAD_PINS:
            raise RuntimeError(f"Pin {gpio} must be TouchPad pin 1 to 14")

    def define_register( self, gpio, name, initial_value ):
        self._add_GPIO_to_list(gpio)

    def define_tempo( self, gpio_a, gpio_b, gpio_switch ):
        self._add_GPIO_to_list(gpio_a)
        self._add_GPIO_to_list(gpio_b)
        self._add_GPIO_to_list(gpio_switch)
        return
    
    def define_midi(self, pin, midi_note, rank, register_name):
        if self.current_driver == "GPIODriver" or self.current_driver == "GPIOServoDriver":
            if not pin:
                raise RuntimeError("GPIO pin blank or 0 for {self.current_driver}")
            # Check if used as gpio elsewhere (but don't check duplicate
            # use as gpio midi, because that's allowed)
            if pin in self.gpiolist:
                raise RuntimeError(f"MIDI GPIO pin already in use: {pin}")
        elif self.current_driver == "MCP23017Driver" or self.current_driver == "PCA9685Driver":
            if not( 0 <= pin <= 15 ):
                raise RuntimeError( f"{self.current_driver} pin number not 0-15 {pin}")
            if pin is None:
                raise RuntimeError("MCP pin blank")
        elif self.current_driver == "MIDISerialDriver":
           if not(0 <= pin <= 1000):
               raise RuntimeError(f'MIDI over serial must have a unique "virtual" pin number for each MIDI note')
        else:
            raise RuntimeError("MIDI pin definition must be preceded by controller definition {self.current_driver=}")     

        if midi_note.is_valid() and  not midi_note.is_correct():
            m = f"MIDI program or note number not in range {self.current_driver=} {pin=} {midi_note=} {rank=} {register_name=}"
            print(m)
            raise RuntimeError(m)


    def define_i2c(self, sda, scl):
        if not sda or not scl:
            raise RuntimeError("SDA or SCL pin blank or 0")
        self.current_I2C += 1
        self.current_MCP_address = ""
        self._add_GPIO_to_list(sda)
        self._add_GPIO_to_list(scl)

    def define_mcp23017_driver(self, address):
        if self.current_I2C == -1:
            raise RuntimeError("MCP23017 definition must be preceded by I2C definition")
        if address is None:
            raise RuntimeError("MCP address blank")
        self._add_to_list(
            f"{self.current_I2C}.{address}",
            self.mcplist,
            f"Duplicate MCP, I2C {self.current_I2C} address {address}",
        )
        self.current_driver = "MCP23017Driver"

    def define_pca9685_driver( self, address, period_us):
        if self.current_I2C == -1:
            raise RuntimeError("PCA9685 definition must be preceded by I2C definition")
        if address is None:
            raise RuntimeError("PCA9685 address blank")
        self._add_to_list(
            f"{self.current_I2C}.{address}",
            self.mcplist,
            f"Duplicate PCA9685, I2C {self.current_I2C} address {address}",
        )
        if  period_us <= 3000:
            raise RuntimeError("Servo period must be at least 3000 usec")

        self.current_driver = "PCA9685Driver"


    def define_gpio_driver( self ):
        self.current_driver = "GPIODriver"
    
    def define_gpioservo_driver( self, period_us  ):
        if  period_us <= 3000:
            raise RuntimeError("Servo period must be at least 3000 usec")
        self.current_driver = "GPIOServoDriver"
        # Defining more than the PWM channels of the ESP32S3 (it has 8)
        # will raise "ValueError: out of PWM channels:8" 

    def define_serial_driver( self, uart, txpin, channel, rxpin ):
        if not( 1<=uart<=2 ):
            raise RuntimeError("UART must be 1 or 2")
        if uart in self.uart_list:
            raise RuntimeError("Duplicate UART definition")
        if not( 0<=channel<=15):
            raise RuntimeError("Channel must be 1 to 16 (internally 0-15)")
        if not txpin or not rxpin:
            raise RuntimeError("UART txpin and rxpin must be specified")
        self.uart_list.append( uart )
        self._add_GPIO_to_list(txpin)
        # If saving new configuration, rxpin MUST be specified.
        self._add_GPIO_to_list(rxpin)
        self.current_driver = "MIDISerialDriver"
    
    def define_servopulse( self, pulse0_us, pulse1_us ):
        from drehorgel import config
        if not( config.rc_min_pulse <= pulse0_us <= config.rc_max_pulse )or \
           not( config.rc_min_pulse <= pulse1_us <= config.rc_max_pulse ):
            raise RuntimeError(f"Servo pulse with must be {config.rc_min_pulse} to {config.rc_max_pulse} microseconds and is {pulse0_us} to {pulse1_us}")
    
    def define_complete(self):
        # Write updated info back to flash
        fileops.write_json(self.new_json, self.output_filename)
        # Changes take effect at next reboot

    
class GPIOstatistics(PinoutParser):
    # Called by webserver.py to provide statistics for the
    # pinout.html page
    def __init__( self, *args ):
        # Get unique ocurrences
        self.used_gpio_pins = set()
        super().__init__(*args)

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

    # for "touchpad" entry
    def define_touchpad(self, gpio, technology):
        self._add_gpio( gpio )
    
    def define_register( self, gpio, *args ):
        self._add_gpio( gpio )
    
    def define_midi(self, pin, *args ):
        if self.current_driver == "GPIODriver" or self.current_driver == "GPIOServoDriver":
            self._add_gpio( pin )

    def define_i2c( self, sda, scl ):
        self._add_gpio( sda )
        self._add_gpio( scl )
 
    def define_tempo( self, gpio_a, gpio_b, gpio_switch ):
        self._add_gpio( gpio_a )
        self._add_gpio( gpio_b )
        self._add_gpio( gpio_switch )
        return

    def define_serial_driver(self, uart, pin, channel, rxpin):
        self._add_gpio( pin )
        self._add_gpio( rxpin )
        return super().define_serial_driver(uart, pin, channel, rxpin)

    def get_used_pins( self ):
        # Sort GPIO pins
        gpiopins = [ x for x in self.used_gpio_pins ]
        gpiopins.sort()
        ESP32_S3_RESERVED_PINS.sort()
        availableGPIO = [ pin for pin in ESP32_S3_AVAILABLE_GPIO_PINS if pin not in gpiopins ]
        availableADC1 = [ pin for pin in _ESP32_S3_ADC1_PINS if pin not in gpiopins ]
        availableTouchpad = [ pin for pin in _ESP32_S3_TOUCHPAD_PINS if pin not in gpiopins ]
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
    


class PinoutList:
    def __init__(self, pinout_folder, pinout_txt_filename ):
        self.pinout_txt_filename = pinout_txt_filename
        self.pinout_folder = pinout_folder
        self.pinout_files = {}
        # self.pinout_files is a dict, key=filename, data=description
        self._fill_pinout_files()
        self.logger = getLogger(__name__)
        self.current_pinout_filename = get_current_pinout( pinout_txt_filename )
        self.logger.info(f"Current pinout {self.current_pinout_filename}")

    def _fill_pinout_files(self):
            # Pinout files must have the form <nnn>_note_<name>.json
            # where <nnn> is the number of notes of the scale and
            # <name> is the name itself, example 20_note_Carl_Frei.json
            # where 20 is the number of notes and Carl_Frei is the name.
        # Examples: 20_note_Carl_Frei.json, 31_note_Raffin.json)
        # self.pinout_files is a dict, key=filename, value=description (initally blank, filled later)
        self.pinout_files = {}
        pattern = re.compile("^[0-9]+_note_.+\\.json$")
        for fn in os.listdir(self.pinout_folder):
            if re.match(pattern, fn):
                # the value of self.pinout_files is the description, 
                # add only when needed
                self.pinout_files[self.pinout_folder + "/" + fn] = ""

        if len(self.pinout_files) == 0:
            # No pinout files, can't work, fatal problem
            self.logger.error("Error: no pinout files found in /data")

    def _read_pinout_txt(self):
        fn = None
        try:
            with open(self.pinout_txt_filename) as file:
                # Return filename of nn_xxxxx.json with pinout info
                fn = file.read()
        except:
            # Return None if not found.
            pass
        return fn

    def set_current_pinout_filename(self, new_pinout_filename):
        if new_pinout_filename not in self.pinout_files:
            raise ValueError # should have been checked by javascript
        fileops.backup(self.pinout_txt_filename)
        with open(self.pinout_txt_filename, "w") as file:
            file.write(new_pinout_filename)
        # Change takes effect at next reboot

    def get_saved_pinout_filename(self):
        return self._read_pinout_txt()

    def get_filenames_descriptions(self):
        # Return list of pairs ( filename, description )
        # Fill descriptions on demand to make initialization
        # faster. This function is only called to fill the pinout.html page
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
                filename, False
            ).get_description()
        return self.pinout_files[filename]

