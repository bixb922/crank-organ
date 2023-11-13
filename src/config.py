# (c) 2023 Hermann Paul von Borries
# MIT License
# Handles config.json and other configuration options
# Also, data file names and folders are defined here.

import time
import json
import os
import network
import ubinascii
import sys
import random


from minilog import getLogger
import fileops

_logger = getLogger( __name__ )
# Password mask for web form
NO_PASSWORD = "*"*15

class Config:
    def __init__( self ):
        self.cfg = {} 
        _logger = getLogger( __name__ )
        
        # Data file/folder names used in the software
        self.CONFIG_JSON  = "data/config.json"
        if fileops.file_exists( "/sd"):
            self.MUSIC_FOLDER = "/sd/"
        else:
            self.MUSIC_FOLDER = "tunelib/"
        self.MUSIC_JSON = "data/tunelib.json"

        self.BATTERY_JSON = "data/battery.json"
        self.ORGANTUNER_JSON = "data/organtuner.json"
        self.SETLIST_JSON = "data/setlist.json"
        self.PINOUT_TXT = "data/pinout.txt"
        self.PINOUT_FOLDER = "data/"
        self.HISTORY_DATABASE = "data/history.db"
        
        # minilog folder defined in minilog module, not here

        
        # Get time.ticks_ms() at boot time. 
        # Does get set to zero on soft reset.
        self.boot_ticks_ms = time.ticks_ms()

        # For ESP32-S3 at 240Mhz, garbage collection takes
        # about 20 to 25 msec for this application
        self.max_gc_time = 30


        # Read config.json
        try:
            self.cfg = fileops.read_json( self.CONFIG_JSON) 

        except Exception as e:
            _logger.exc( e, f"Could not read {self.CONFIG_JSON}, loading fallback configuration" )
            self.cfg = {}

        # Load a fallback configuration, populate cfg with missing values if any
        # If that value is saved, information gets complemented.
        # Also, the save() function relies on all keys be present. Only
        # keys present in cfg can be updated, no new keys added.
        # Also: initially there does not need to be a config.json.
        # After the first change, config.json is complete.
        fallback = {
            "description" : "Your ESP32-S3 device",
            "name": "esp32s3",

            "access_point1": "wifi_SSID_1",
            "password1": "password1",
            "access_point2": "wifi_SSID_2",
            "password2": "password2",
            "ap_password": "drehorgel",
            "password_required": False,

            "ap_ip": "192.168.144.1",

            "ap_max_idle": 120,
            "idle_deepsleep_minutes": 15,
            "battery_watt_hours": 24,
            "solenoid_watts": 1.6,
            "fixed_watts": 0.6,
            "battery_heartbeat_duration": 0,
            "battery_heartbeat_period": 0,
            "max_polyphony": 9,
            
            "touchpad_big_change": 20000,
            "tzidentifier": "America/Santiago",

            "initial_page": "index",
            "modes":["play", "tuner", "config"],

            "webserver_cache": True,
            # Firefox caps max_age at 86400 seconds, Chromium at 7200 seconds
            "max_age": 300,

            "mic_test_mode": False,
        }
        # Fill in all missing fields from fallback
        for k,v in fallback.items():
            if k not in self.cfg:
                self.cfg[k] = v

        # Cypher passwords, if not done already
        if password_manager._cypher_all_passwords( self.cfg ):
            # Rewrite config.json with cyphered passwords.
            fileops.write_json( self.cfg,  self.CONFIG_JSON, keep_backup=False )
            _logger.info("Passwords cyphered")


        self.wifi_mac = ubinascii.hexlify( network.WLAN(network.STA_IF).config("mac")).decode()

        _logger.info(f"Config {self.cfg['description']} wifi_mac={self.wifi_mac} hostname and AP SSID={self.cfg['name']}")

        
    def get_config( self ):
        # Get copy of complete configuration, to be
        # sent to client (except passwords)

        c = dict( self.cfg )
        c["password1"] = NO_PASSWORD 
        c["password2"] = NO_PASSWORD 
        c["ap_password"] = NO_PASSWORD 
        c["repeat_ap_password"] = NO_PASSWORD
        return c
                                  


    def get_int( self, item, default=None ):
        # Return configuration item as integer, apply default if error
        n = self.cfg.get( item, default )     
        if n is None:
            return None
        try:
            return int( n )
        except:
            _logger.error(f"Config.json item {item} not an integer")
            return default

    def get_float( self, item, default=None ):
        # Return configuration item as floating point
        n = self.cfg.get( item, default )     
        if n is None:
            return None
        try:
            return float( n )
        except:
            _logger.error(f"Config.json item {item} not a floating point number")
            return default

    
    def save( self, newconfig ):
        # Save new configuration, validate before storing  
        # Authentication is already done by webserver.py
        # Validate data received from config.html
        for k,v in newconfig.items():
            if k in ( "max_age", "ap_max_idle",
                    "idle_deepsleep_minutes",
                    "solenoid_resistance", "touchpad_big_change",
                    "max_polyphony", "battery_heartbeat_duration",
                    "battery_heartbeat_period"):
                try:
                    newconfig[k] = int(v)
                except:
                    return f"Error: {k} is not an integer"

            elif k in ( "solenoid_watts", "fixed_watts", 
                       "battery_watt_hours" ):
                try:
                    newconfig[k] = float( v )
                except:
                    return f"Error: {k} is not float"

            elif k == "name":
                # Validate host name
                name = newconfig[k]
                if len(name) > 15:
                    return "Error: Host name exceeds 15 characters"
                u = name.upper()
                for s in u:
                    if not( "A" <= s <= "Z" or "0" <= s <= "9"):
                        return "Host name is not A-Z, a-z, 0-9"
                if not( "A" <= u[0:1] <="Z"):
                    return "Error: Host name does not start with letter"
            elif k == "ap_password":
                if len(v) < 9:
                    return "Error: Password shorter than 9 characters"

        # Copy newconfig into configuration

        # Update only keys that are already in config
        for k in self.cfg:
            if k in newconfig:
                self.cfg[k] = newconfig[k]

        # Cypher passwords if not cyphered
        password_manager._cypher_all_passwords( self.cfg )
        
        fileops.write_json( self.cfg,  self.CONFIG_JSON )

        return "ok"

    
    
PASSWORD_PREFIX = "@cyphered_"
class PasswordManager:
        
    # Password are stored cyphered in config.cfg
    def _get_key( self ):
        from esp32 import NVS
        nvs = NVS("drehorgel")
        key = bytearray(16)
        try:
            nb = 0
            nb = nvs.get_blob("aeskey", key )
        except OSError:
            _logger.info( "Generating new key" )
            nb = 0
        if nb < 16:
            key = os.urandom(16)
            nvs.set_blob("aeskey", key )
        return key

    def _cypher_password( self, password ):
        #>>>TODO: ADD SALT
        if not isinstance(password, str):
            raise ValueError("Can't cypher object that isn't str")
        if password.startswith(PASSWORD_PREFIX):
            raise ValueError("Can't cypher twice")

        from ucryptolib import aes
        pass_encoded = password.encode()
        pass_with_len = bytearray(1)
        pass_with_len[0] = len(pass_encoded)
        pass_with_len.extend( pass_encoded )
        while len(pass_with_len)%16 != 0:
            pass_with_len.append(0)
        c = aes( self._get_key(), 1 ).encrypt( pass_with_len )
        return PASSWORD_PREFIX + ubinascii.hexlify( c ).decode()

    def _uncypher_password( self, c ):  
        if not isinstance(c, str):
            raise ValueError("Can't uncypher object that isn't str")
        if not c.startswith(PASSWORD_PREFIX):
            # Not cyphered, no need to do magic     
            return c   
        c = ubinascii.unhexlify( c[len(PASSWORD_PREFIX):] )
        from ucryptolib import aes
        pass_with_len = aes( self._get_key(), 1 ).decrypt( c )
        passlen = pass_with_len[0]
        return pass_with_len[1:].decode()[0:passlen]

    def _cypher_all_passwords( self, cfg ):
        # Cyphers passwords in config.json if not yet cyphered
        # Save changes to flash
        changed = False
        for k, v in cfg.items():
            if not isinstance(v, str):
                continue
            if "password" in k:
                if v.startswith(PASSWORD_PREFIX):
                    # Don't cypher again
                    continue
                _logger.info(f"Cypher {k}" )
                cfg[k] = self._cypher_password( v )
                changed = True
        return changed
        

    # Public methods
    def get_password( self, pwdname ):
        # Used here and by webserver for http authentication
        pwd = config.cfg[pwdname]
        return self._uncypher_password( pwd )


    # Services to verify password (called by webserver)
    def verify_password( self, password ):
        return password == self.get_password("ap_password")

password_manager = PasswordManager( )
config = Config()


