# (c) 2023 Hermann Paul von Borries
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
NO_PASSWORD = "*" * 15
_DEFAULT_PASSWORD = const("password") 

class Config:
    def __init__(self):
        # Get time.ticks_ms() at boot time.
        # Gets set to zero on soft reset.
        self.boot_ticks_ms = time.ticks_ms()

        
        self.cfg = {}

        # Data file/folder names used in the software
        self.TUNELIB_FOLDER = "tunelib/"
        self.PURGED_FOLDER = "tunelib_purged/"
        if fileops.file_exists("/sd"):
            self.TUNELIB_FOLDER = "/sd/" + self.TUNELIB_FOLDER
            self.PURGED_FOLDER = "/sd/" + self.PURGED_FOLDER
    
        
        # minilog folder/filenames defined in minilog module, not here
        # Timezone file/folder defined in timezone module, not here
        self.BATTERY_CALIBRATION_JSON = "data/battery_calibration.json"
        self.BATTERY_JSON = "data/battery.json"
        self.CONFIG_JSON = "data/config.json"
        self.CURRENT_SETLIST_JSON = "data/setlist_current.json"
        self.DRUMDEF_JSON = "data/drumdef.json"
        self.HISTORY_JSON = "data/history.json"
        self.LYRICS_JSON = "data/lyrics.json"
        self.ORGANTUNER_JSON = "data/organtuner.json"
        self.PINOUT_TXT = "data/pinout.txt"
        self.PINOUT_FOLDER = "data"
        self.STORED_SETLIST_JSON = "data/setlist_stored.json"
        self.SYNC_TUNELIB = "data/sync_tunelib"
        self.TUNELIB_JSON = "data/tunelib.json"
        
        # Read config.json
        self.cfg = fileops.read_json(
                self.CONFIG_JSON, 
                default={} )

        # Load a fallback configuration, populate cfg with missing values if any
        # If that value is saved, information gets complemented.
        # Also, the save() function relies on all keys be present. Only
        # keys present in cfg can be updated, no new keys added.
        # Also: initially there does not need to be a config.json.
        # After the first change, config.json is complete.
        fallback = {
            "description": "Your ESP32-S3 device",
            "name": "esp32s3",
            "access_point1": "wifi_SSID_1",
            "password1": _DEFAULT_PASSWORD,
            "access_point2": "wifi_SSID_2",
            "password2": _DEFAULT_PASSWORD,
            "ap_password": _DEFAULT_PASSWORD,
            "password_required": False,
            "ap_ip": "192.168.144.1",
            "ap_max_idle": 120, 
            "idle_deepsleep_minutes": 15,
            "battery_heartbeat_duration": 0,
            "battery_heartbeat_period": 0,
            "max_polyphony": 9,
            "touchpad_big_change": 20000,
            
            "webserver_cache": True,
            # Firefox caps max_age at 86400 seconds=1 day, Chromium at 7200 seconds=2 hours
            "max_age": 1800,
            
            "mic_test_mode": False,
            "mic_signal_low": -18,
            "mic_store_signal": False,
            
            "servernode": "192.168.100.19:8080", # Only used if mcserver.py is present
            "serverpassword": "password3", # Only used if mcserver.py is present

            "automatic_delay": 0,
            "tempo_follows_crank": False,
            "pulses_per_revolution": 24,
            "lower_threshold_rpsec": 0.4,
            "higher_threshold_rpsec": 0.7,
            "normal_rpsec": 1.2,
            "crank_lowpass_cutoff": 1.2,
            "rotary_tempo_mult": 1,
            "tuning_frequency": 440,
            "tuning_cents": 5,
        }
        # Populate missing keys from fallback
        missing_items = {k: fallback[k] for k in set(fallback.keys()) - set(self.cfg.keys())}
        self.cfg.update(missing_items)
        for k in missing_items:
            _logger.debug(f"Adding configuration key '{k}'")

        # Delete surplus keys
        for k in set(self.cfg.keys()) - set(fallback.keys()):
            del self.cfg[k]
            _logger.debug(f"key '{k}' is not needed, now deleted")

        # Encrypted passwords, if not done already
        if PasswordManager().encrypt_all_passwords(self.cfg):
            # A password had to be encrypted.
            # Rewrite config.json with encrypted passwords.
            # No backup, the backup would show the passwords
            fileops.write_json(self.cfg, self.CONFIG_JSON, keep_backup=False)
            _logger.info("Passwords encrypted")

        # Get WiFi MAC address (only to show in diag.html)
        self.wifi_mac = binascii.hexlify(
            network.WLAN(network.STA_IF).config("mac")
        ).decode()

        # Give AP more time while WiFi station mode is not fully configured
        if self.cfg["access_point1"] == fallback["access_point1"]:
            # WiFi not configured yet, give AP mode plenty
            # of time. Alter AP max idle temporarily.
            self.cfg["ap_max_idle"] = 3600

        _logger.debug( f"Config {self.cfg['description']} wifi_mac={self.wifi_mac} hostname and AP SSID={self.cfg['name']}"  )

    def get_config(self)->dict:
        # Get copy of complete configuration, to be
        # sent to client (except passwords)

        c = dict(self.cfg)
        c["password1"] = NO_PASSWORD
        c["password2"] = NO_PASSWORD
        c["ap_password"] = NO_PASSWORD
        c["repeat_ap_password"] = NO_PASSWORD
        c["serverpassword"] = NO_PASSWORD
        return c

    def get_int(self, item, default=None):
        # Return configuration item as integer, apply default if error
        n = self.cfg.get(item, default)
        if n is None:
            return None
        try:
            return int(n)
        except ValueError:
            _logger.error(f"Config.json item {item} not an integer")
            return default

    def get_float(self, item, default=None)->float|None:
        # Return configuration item as floating point
        n = self.cfg.get(item, default)
        if n is None:
            return None
        try:
            return float(n)
        except ValueError:
            _logger.error(
                f"Config.json item {item} not a floating point number"
            )
            return default
    # >>> implement get() and get_bool()
    
    def save(self, newconfig):
        # Save new configuration, validate before storing
        # Authentication is already done by webserver.py
        # Validate data received from config.html
        for k, v in newconfig.items():
            if k in (
                "max_age",
                "ap_max_idle",
                "idle_deepsleep_minutes",
                "solenoid_resistance",
                "touchpad_big_change",
                "max_polyphony",
                "battery_heartbeat_duration",
                "battery_heartbeat_period",
                "automatic_delay",
                "tuning_cents"
            ):
                try:
                    newconfig[k] = int(v)
                except ValueError:
                    return f"Error: [{k}]={v} is not an integer"

            elif k in (
                "mic_signal_low",
                "pulses_per_revolution",
                "lower_threshold_rpsec",
                "higher_threshold_rpsec",
                "normal_rpsec",
                "crank_lowpass_cutoff",
                "rotary_tempo_mult",
                "tuning_frequency",
            ):
                try:
                    newconfig[k] = float(v)
                except ValueError:
                    return f"Error: [{k}]={v} is not float"

                if k == "mic_signal_low" and newconfig[k] > 0:
                    return f"Error: [{k}]={v} must be negative"

            elif k == "name":
                # Validate host name
                name = newconfig[k]
                if len(name) > 15:
                    return "Error: Host name exceeds 15 characters"
                if not re.match("[A-Za-z][A-Za-z0-9]*", name):
                    return "Error: Host name is not alphanumeric"
            elif k == "ap_password":
                if len(v) < 9:
                    return "Error: Password shorter than 9 characters"
            elif "password" in k and v == NO_PASSWORD:
                return "Error: overwriting password with ***, programming error?"

        # Copy newconfig into configuration

        # Update only keys that are already in config
        # Don't use self.cfg.update() because it could add new keys
        for k in self.cfg:
            if k in newconfig:
                self.cfg[k] = newconfig[k]

        # encrypt passwords if not encrypted
        PasswordManager().encrypt_all_passwords(self.cfg)

        fileops.write_json(self.cfg, self.CONFIG_JSON)

        return
    
    def get_password(self, pwdname)->str:
        # Used by self.verify_password() and by wifimanager
        pwd = self.cfg[pwdname]
        return PasswordManager().decrypt_password(pwd)

    # Used by webserver to verify hashed seed+hashed password
    # sent by client
    def verify_password(self, client_password, seed ):
        # Must be same algorithm as common.js: hashWithSeed()
        h = sha256( (seed+"_"+self.get_password("ap_password")).encode()).digest()
        hexhash =  binascii.hexlify( h ).decode() 
        return client_password == hexhash
    

PASSWORD_PREFIX = "@encrypted_"


class PasswordManager:
    # Password are stored encrypted in config.cfg
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
        for k, v in cfg.items():
            if not isinstance(v, str):
                continue
            if "password" in k:
                if v.startswith(PASSWORD_PREFIX):
                    # Don't encrypt again
                    continue
                cfg[k] = self.encrypt_passwords(v)
                changed = True
        return changed


