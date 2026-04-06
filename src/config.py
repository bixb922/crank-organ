# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
# Handles config.json and other configuration options
# Also, data file names and folders are defined here.
from micropython import const
import time
import os
import network
import binascii
import minilog
import fileops
import re
from hashlib import sha256

# One logger for both Config and PasswordManager
_logger = minilog.getLogger(__name__)
# Password mask for web form
_PASSWORD_MASK = "*" * 15
# Initial password when just installed
_DEFAULT_PASSWORD = const("password") 


class Config:
    def __init__(self, show_log ):
        # Capital letters config attributes cannot be changed in config.json

        # Get time.ticks_ms() at boot time.
        # Gets set to zero on soft reset.
        self.BOOT_TICKS_MS = time.ticks_ms()

        # Data file/folder names used in the software
        self.TUNELIB_FOLDER = "tunelib/"
        self.PURGED_FOLDER = "tunelib_purged/"
        if fileops.file_exists("/sd"):
            self.TUNELIB_FOLDER = "/sd/" + self.TUNELIB_FOLDER
            self.PURGED_FOLDER = "/sd/" + self.PURGED_FOLDER
        
        # Upper case: config items that cannot be set with config.json
        # minilog folder/filenames defined in minilog module, not here
        # Timezone file/folder defined in timezone module, not here
        self.DATA_FOLDER = "data/"
        self.BATTERY_CALIBRATION_JSON = "data/battery_calibration.json"
        self.BATTERY_JSON = "data/battery.json"
        self.CONFIG_JSON = "data/config.json"
        self.DRUMDEF_JSON = "data/drumdef.json"
        self.HISTORY_JSON = "data/history.json"
        self.LYRICS_JSON = "data/lyrics.json"
        self.ORGANTUNER_JSON = "data/organtuner.json"
        self.PINOUT_TXT = "data/pinout.txt"
        self.PINOUT_FOLDER = "data"
        self.SETLIST_TITLES_JSON = "data/setlist_titles.json"
        self.SYNC_TUNELIB = "data/sync_tunelib.json"
        self.TUNELIB_JSON = "data/tunelib.json"
        
        # Lower letter config attributes can be changed with config.json/config.html
        # Set default values and data types. 
        # Defined data type is used for validations/conversions later.
        # Data types can be str, int, float, bool.
        self.description = "Your ESP32-S3 device"
        self.name = "esp32s3"

        # WiFi and passwords
        self.access_point1 = "wifi_SSID_1"
        self.password1 = _DEFAULT_PASSWORD
        self.access_point2 = "wifi_SSID_2"
        self.password2 = _DEFAULT_PASSWORD
        self.ap_password = _DEFAULT_PASSWORD
        self.password_required = False
        self.ap_ip = "192.168.144.1"
        self.ap_max_idle = 180 
        self.advertise_bt = False

        # Power management
        self.battery_heartbeat_duration = 0
        self.battery_heartbeat_period = 0
        self.idle_deepsleep_minutes = 15

        # Driver parameters
        self.touchpad_big_change = 20_000
        self.max_polyphony = 9
        self.i2c_frequency_khz = 100 # 100, 200, 400

        # Webserver parameters
        self.webserver_cache = True
        self.max_age = 1800

        # Microphone and tuner
        self.mic_test_mode = False
        self.mic_signal_low = -18.0
        self.mic_store_signal = False
        self.mic_amplitude = False
        self.tuning_frequency = 440.0
        self.tuning_cents = 10

        # MC server
        self.servernode = ""
        self.serverpassword = "password3"

        # Music and crank
        self.automatic_delay = 0
        self.tempo_follows_crank = False
        self.pulses_per_revolution = 100.0
        self.lower_threshold_rpsec = 0.4
        self.higher_threshold_rpsec = 0.7
        self.normal_rpsec = 1.2
        self.crank_lowpass_cutoff = 1.2
        self.rotary_tempo_mult = 1.0
        self.multiple_setlists = False 
        self.wait_stop_turning = True
     
        self.barrel_mode = False
        
        # RC Servos 
        self.rc_max_moving = 10
        self.rc_moving_time = 80 # msec
        self.rc_pwm_auto_off = True
        
        # Logger level 
        self.log_debug = False 

        # History
        self.auto_purge_history = 0

        # Read data/config.json and validate
        cfg = self.read_config()
        # No need to delete surplus keys, validation did that already

        # Encrypted passwords, if not done already
        if PasswordManager().encrypt_all_passwords(cfg):
            # A password had to be encrypted.
            # Rewrite config.json with encrypted passwords.
            # No backup, the backup would show the passwords
            fileops.write_json(cfg, self.CONFIG_JSON, keep_backup=False)
            _logger.info("Passwords encrypted")


        # Merge config.json into self.
        # Variables not in config.json are left with default value
        for k, v in cfg.items():
            setattr( self, k, v )

        # Give AP more time while WiFi station mode is not fully configured
        if "access_point1" not in cfg:
            # WiFi not configured yet, give AP mode plenty
            # of time. Alter AP max idle temporarily.
            self.ap_max_idle = 3600

        if show_log:
            # Get WiFi MAC address (only to show in diag.html)
            wifi_mac = binascii.hexlify(
                network.WLAN(network.STA_IF).config("mac"), "-"
            ).decode()        
            _logger.debug( f"Config {self.description}, WiFi mac={wifi_mac}, hostname and AP SSID={self.name}"  )
        

    def read_config( self ):
        # Read config.json
        cfg = fileops.read_json(self.CONFIG_JSON, default={} )
        
        # Validate config read with current definition
        # Remove incorrect entries so that a default value is used.
        # That prevents crashes due to incorrect contents of config.json
        self._validate_config( cfg, on_error="remove" )
        
        return cfg

    
    def get_current_config( self ):
        # export current configuration, hide passwords, return dict.
        # This is used by the browser/web client to get configuration information
        cfg = { k: v for k, v in self.__dict__.items()
                if self._is_config_variable(k) }
        for k in ("password1", "password2", "ap_password", "repeat_ap_password", "serverpassword"):
            cfg[k] = _PASSWORD_MASK
        return cfg

    def get_stored_config( self ):
        # Get fresh data from flash as dict.
        # This is used by the browser/web client to get configuration information
        # Use a new instance of class Config to read this, so
        # current configuration is not touched.
        # When config.json has been just changed, this will return
        # the config.json. self still has the old values.
        return Config(False).get_current_config()

    def _validation_function( self, datatype ):
        return {
            "int": int, "str": str, "bool": bool, "float": float
        }[datatype]
    
    def _get_type( self, k ):
        # Get type of configuration variable k
        # If not a configuration variable (wrong name or k is a method of this class)
        # then raise AttributeError.
        # If not correct value data type, raise ValueError
        # Configuration variables are in lower case.
        if "a" <= k[0:1] <= "z":
            datatype = type(getattr(self, k)).__name__
            try:
                # Check valid data type (int/bool/float/str)
                self._validation_function( datatype )
                return datatype
            except KeyError:
                pass # go on to raise Attribute Error
        # Not a configuration variable
        raise AttributeError
        
    def _is_config_variable( self, k ):
        try:
            self._get_type( k )
            return True
        except:
            pass # return false
        
    def _validate( self, k, v ):
        # Calls validation function for variable named k, value v
        # Returns v converted to correct data type 
        # Raises AttributeError if k is not a configuration variable
        # Raises ValueError if v is not acceptable for the data type of k
        datatype = self._get_type( k )
        try:
            v = self._validation_function(datatype)(v)
            # Some special validations
            if k == "ap_password":
                self._validate_password( v )
            elif k == "name":
                self._validate_hostname( v )
            return v
        except ValueError:
            raise ValueError( f"Error: [{k}]={v} is not {datatype}" )
    
    def save(self, newconfig):
        # Called from "Save changes" button of config.html page.
        # newconfig is a dictionary with the changed values.
        self._validate_config( newconfig, on_error="raise")
        cfg = fileops.read_json( self.CONFIG_JSON, default={} )
        cfg.update( newconfig )
        PasswordManager().encrypt_all_passwords( cfg )
        fileops.write_json(cfg, self.CONFIG_JSON )
        return
    
    def get_password(self, pwdname)->str:
        # Used by self.verify_password() and by wifimanager
        return PasswordManager().decrypt_password(getattr( self, pwdname ))

    # Used by webserver to verify hashed seed+hashed password
    # sent by client
    def verify_password(self, client_password, seed ):
        # Must be same algorithm as common.js: hashWithSeed()
        h = sha256( (seed+"_"+self.get_password("ap_password")).encode()).digest()
        return client_password == binascii.hexlify( h ).decode() 
    
    def _validate_hostname( self, name ):
        if len(name) > 15 or  not re.match("[A-Za-z][A-Za-z0-9]*", name):
            raise ValueError( "Error: hostname '{name}' exceeds 15 characters or is not alphanumeric" )

    def _validate_password( self, v ):
        # Only needed for AP password
        if not( v.startswith(PASSWORD_PREFIX) or v == _DEFAULT_PASSWORD or v == _PASSWORD_MASK ):
            if len(v) < 9:
                raise ValueError( "Error: Password {k} shorter than 9 characters" )


    def _validate_config( self, cfg, on_error ):
        # on_error can be "raise" or "remove"
        for k, v in cfg.items():
            try:
                # Validate and convert to correct data type
                cfg[k] = self._validate( k, v )
            except ValueError:
                if on_error == "raise":
                    raise
                del cfg[k]   
                _logger.info(f"[{k}]={v} value error, removing")
            except AttributeError:
                # Normally due to obsolete keys in config.json
                del cfg[k]
                _logger.info(f"[{k}] not needed, removing")
            except Exception as e:
                # Make this work anyhow, use default value.
                # That is better than crashing....
                del cfg[k]
                _logger.exc( e, "Unhandled exception validating configuration item [{k}]={v} ")



PASSWORD_PREFIX = "@encrypted_"

class PasswordManager:
    # Password are stored encrypted in config instance
    # Although this doesn't make the ESP32-S3 secure....
    def _get_key(self)->bytes:
        from esp32 import NVS
        # Give NVS some protection, but if someone
        # can have access to USB and/or insert some code,
        # the contents can be obtained anyhow.
        nvs = NVS(_DEFAULT_PASSWORD)
        key = bytearray(16)
        try:
            nb = 0
            nb = nvs.get_blob("aeskey", key)
        except OSError:
            _logger.info("Generating new key")
            nb = 0
        if nb < 16:
            key = os.urandom(16)
            nvs.set_blob("aeskey", key)
        return key

    def encrypt_passwords(self, password)->str:
        if not isinstance(password, str):
            raise ValueError("Can't encrypt object that isn't str")
        if password.startswith(PASSWORD_PREFIX):
            raise ValueError("Can't encrypt twice")

        pass_encoded = password.encode()
        # Space for password, 4 bytes initial vector, 4 bytes check, 1 byte
        # encoded length, the encoded password, and 1 extra just in case
        pass_buffer_len = len(pass_encoded) + 4 + 4 + 1 + 1
        # AES likes buffer length multiple of 16
        pass_buffer_len += 16 - (pass_buffer_len % 16)
        # Fill buffer with random so unused bytes act as initial vector
        # This makes equal passwords encrypt differently.
        pass_buffer = bytearray(os.urandom(pass_buffer_len))
        # Add text to help _decrypt_password recognize if correctly decrypted
        pass_buffer[4:8] = b"salt"
        # Add password length
        pass_buffer[8] = len(pass_encoded)
        # Add password
        pass_buffer[9 : 9 + len(pass_encoded)] = pass_encoded

        from cryptolib import aes

        c = aes(self._get_key(), 1).encrypt(pass_buffer)

        return PASSWORD_PREFIX + binascii.hexlify(c).decode()

    def decrypt_password(self, c)->str:
        if not isinstance(c, str):
            raise ValueError("Can't decrypt object that isn't str")
        if not c.startswith(PASSWORD_PREFIX):
            # Not encrypted, no need to do magic
            return c
        c = binascii.unhexlify(c[len(PASSWORD_PREFIX) :])
        from cryptolib import aes

        pass_buffer = aes(self._get_key(), 1).decrypt(c)
        # If error, return phony password instead of
        # raising an error. Raising an error will abort the
        # software, better to continue with default password
        # to maximize access to software.
        if len(pass_buffer) < 10:
            _logger.error("Could not decrypt password, wrong length")
            return _DEFAULT_PASSWORD
        if pass_buffer[4:8] != b"salt":
            _logger.error("Could not decrypt password, wrong key")
            return _DEFAULT_PASSWORD
        # pass_buffer[8] has the length of the encoded password.
        pass_encoded = pass_buffer[9 : 9 + pass_buffer[8]]

        return pass_encoded.decode()

    def encrypt_all_passwords(self, cfg)->bool:
        # encrypts passwords in config.json if not yet encrypted
        # Save changes to flash
        changed = False
        for k in ("password1", "password2", "ap_password", "repeat_ap_password", "serverpassword"):
            if k in cfg and not cfg[k].startswith(PASSWORD_PREFIX):
                cfg[k] = self.encrypt_passwords(cfg[k])
                changed = True
        return changed

