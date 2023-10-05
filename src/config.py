
import time
import json
import os
import gc
import network
import ubinascii
import sys

from minilog import getLogger, set_time_zone_offset
_logger = getLogger( __name__ )

CONFIG_JSON  = const("config.json")
FLASH_MUSIC_FOLDER = const("tunelib/")
SD_MUSIC_FOLDER = const("/sd/tunelib/")
# Music folder is either sd card or flash (but not both)
MUSIC_FOLDER = None # Configured by config._init
# Folder of MUSIC_JSON is MUSIC_FOLDER
MUSIC_JSON = "tunelib.json"

DATA_FOLDER = const("data")
BATTERY_JSON = const("data/battery.json")
ORGANTUNER_JSON = const("data/organtuner.json")
SETLIST_JSON = const("data/setlist.json")
PINOUT_FILE = const("data/pinout.txt")

NO_PASSWORD = "*"*15

def _init():

    global cfg 
    global large_memory
    global max_gc_time, sdcard
    global architecture, wifi_mac, boot_ticks_ms
    global MUSIC_FOLDER, MUSIC_JSON
    
    # Get time.ticks_ms() at boot time. 
    # Does get set to zero on soft reset.
    boot_ticks_ms = time.ticks_ms()
    
    # Get RAM size
    bytes_RAM = gc.mem_free() + gc.mem_alloc() # Takes 500 msec with 8Mb RAM
            
    large_memory = True if bytes_RAM > 4_000_000 else False
    
    # Garbage collection times.
    # machine.freq(240MHz) is about 3x faster than machine.freq(80Mhz)
    # Normal times for gc:
    # Wemos Lolin D32 Pro ESP32 4MB RAM
    # machine.freq=80Mhz -> gc.collect()==66 milisec
    # machine.freq=240Mhz -> gc.collect8)=46 millisec
    # YD-ESP32-S3 8MB RAM
    # machine.freq=80Mhz -> gc.collect() == 175 millisec
    # machine.freq=240 Mhz -> gc.collect == 59 millisec
    # Plain ESP32
    # machine.freq=80Mhz -> gc.collect() == 17 millisec
    # machine.freq=240Mhz -> gc.collect() = 5 millisec
    # 8MB RAM, 240Mhz absolutely worst case (irreal): 536 ms for 8MB and 216.000 small objects. Bad case: 333 ms.
        
    if bytes_RAM > 4_000_000:
        max_gc_time = 20 # msec with Micropython 1.20 new gc module
        # YD-ESP32-S3 8MB minimum gc time 59 ms at 240 Mhz, minimum 175 ms at 80Mhz.
        large_memory = True
    elif bytes_RAM > 4_000_000:
        max_gc_time = 20 # msec. Normal time=70 to 120 for ESP32 with 4MB
        large_memory = True
    else:
        max_gc_time = 10 # msec for plain ESP32, average 5 msec.
        large_memory = False
        # Most probably this does not run in 110 kb anymore. Not tested.

    architecture = "ESP32"
    if "ESP32S3" in os.uname().machine:
        architecture = "ESP32S3"
        
    wifi_mac = ubinascii.hexlify( network.WLAN(network.STA_IF).config("mac")).decode()

    # Check for SD card
    sdcard = False
    MUSIC_FOLDER = FLASH_MUSIC_FOLDER
    try:
        # See if a file system is mounted at /sd
        # Don't know if its just a folder or a real VFS.
        # os.statvfs("/sd") returns a 10 element tuple of any
        # folder, so the only way to distiguish is by the values...?
        os.stat("/sd")
        sdcard = True
        _logger.info("SD card detected at /sd")
        MUSIC_FOLDER = SD_MUSIC_FOLDER
    except:
        pass
    
    MUSIC_JSON = MUSIC_FOLDER + MUSIC_JSON
    
    # Read config.json
    try:
        with open(CONFIG_JSON) as file:
            cfg = json.load( file )

    except Exception as e:
        _logger.exc( e, f"Could not read {CONFIG_JSON}" )
        cfg = {}
        
    # Load a fallback configuration, populate cfg with missing values if any
    # If that value is saved, information gets complemented.
   
    fallback = {
        "description" : "Your ESP32-S3 device",
        "name": "esp32s3",
		
        "access_point1": "wifi_SSID_1",
        "password1": "password1",
        "access_point2": "wifi_SSID_2",
        "password2": "password2",
        "ap_password": "drehorgel",
		
        "ap_ip": "192.168.144.1",
		
        "ap_max_idle": 120,
        "idle_deepsleep_minutes": 15,
        "battery_watt_hours": 24,
        "solenoid_resistance": 90,
		
        "touchpad_big_change": 10000,
        "time_zone_offset": 0.0,
		
        "initial_page": "index",
        "modes":["play", "tuner", "config"],
		
        "webserver_cache": True,
		# Firefox caps max_age at 86400, Chromium at 10 minutes.
        "max_age": 7200,
        "mic_test_mode": False,
    }
    for k,v in fallback.items():
        if k not in cfg:
            cfg[k] = v

    # Cypher passwords, if not done already
    _cypher_all_passwords( cfg )
    
    _logger.info(f"Config {cfg['description']} {architecture=} {wifi_mac=} hostname=AP-ssid=BLE={cfg['name']}")

    # Set time zone for minilog
    set_time_zone_offset( float( cfg["time_zone_offset"] ))
    
def _get_key():
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

PASSWORD_PREFIX = "@cyphered_"
def _cypher_password( password ):
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
    c = aes( _get_key(), 1 ).encrypt( pass_with_len )
    return PASSWORD_PREFIX + ubinascii.hexlify( c ).decode()

def _uncypher_password( c ):  
    if not isinstance(c, str):
        raise ValueError("Can't uncypher object that isn't str")
    if not c.startswith(PASSWORD_PREFIX):
        # Not cyphered, no need to do magic     
        return c   
    c = ubinascii.unhexlify( c[len(PASSWORD_PREFIX):] )
    from ucryptolib import aes
    pass_with_len = aes( _get_key(), 1 ).decrypt( c )
    passlen = pass_with_len[0]
    return pass_with_len[1:].decode()[0:passlen]
   

def _cypher_all_passwords( cfg ):
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
            cfg[k] = _cypher_password( v )
            changed = True
    if changed:
        # This is done only once.
        with open( CONFIG_JSON, "w") as file:
            json.dump( cfg, file )
        _logger.info("Passwords cyphered")
    return cfg


# Services to change configuration called by webserver
def verify_password( password ):
    return password == get_password("ap_password")

def get_password( pwdname ):
    pwd = cfg[pwdname]
    return _uncypher_password( pwd )

def get_config():
    global cfg
    c = dict( cfg )
    c["password1"] = NO_PASSWORD 
    c["password2"] = NO_PASSWORD 
    c["ap_password"] = NO_PASSWORD 
    c["repeat_ap_password"] = NO_PASSWORD
    return c

def get_int( item, default=None ):
    # Return configuration item as integer, apply default if error
    n = cfg.get( item, default )     
    if n is None:
        return None
    try:
        return int( n )
    except:
        _logger.error(f"Config.json item {item} not an integer")
        return default

def get_float( item, default=None ):
    # Return configuration item as floating point
    n = cfg.get( item, default )     
    if n is None:
        return None
    try:
        return float( n )
    except:
        _logger.error(f"Config.json item {item} not a floating point number")
        return default

    
def save( newconfig ):
    global cfg
    
    # Validate data received from config.html
    for k in newconfig:
        if k in ["max_age", "ap_max_idle",
                "idle_deepsleep_minutes", "battery_watt_hours", "mic_gpio",
                "neopixel_gpio", "tachometer_gpio"]:
            try:
                newconfig[k] = int(newconfig[k])
            except:
                return f"Error: {k} is not an integer"
        if k == "time_zone_offset":
            try:
                newconfig[k] = float( newconfig[k] )
            except:
                return f"Error: {k} is not float"
            
    if "name" in newconfig:
        name = newconfig[k]
        if len(name)>15:
            return "Error: Host name exceeds 15 characters"
        u = name.upper()
        for s in u:
            if not( "A"<=s<="Z" and "0"<=s<="9"):
                return "Host name is not A-Z, a-z, 0-9"
        if not( "A"<=u[0:1]<="Z"):
            return "Error: Host name does not start with letter"
 
    if not verify_password( newconfig["password"]):
        return "Password incorrect"
    
    # Password ok, copy newconfig into configuration

    # Update only keys that are already in config
    for k in cfg:
        if k in newconfig:
            cfg[k] = newconfig[k]

    _cypher_all_passwords( cfg )
    with open( CONFIG_JSON, "w") as file:
        json.dump( cfg, file )

    return "ok"

_init()
