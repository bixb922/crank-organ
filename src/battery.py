# (c) 2023 Hermann Paul von Borries
# MIT License
# Tallies battery usage
import asyncio
from machine import ADC, Pin
import json
import time
import gc

from minilog import getLogger

import config
import solenoid
import scheduler

_UPDATE_EVERY_SECONDS = const(60) # update readings every 60 seconds

_ESP32_WATTS = 0.053*5/0.9 # 54mA at 5V. Efficiency of DC-DC conversion 90%
# For ESP32-S3 dongle measures 393mAh for 7:23hrs = 53mAh playing music,
# no solenoids, but with browser/WiFi connected
# 23 minutes operating = 29 mAh measured including startup
# With both AP and STA: 120mA (AP mode starts a lot, is turned off after some minutes)
# While processing a web request: 120 mA for a short time.
# Added a few mA for MCP23017, only 50 uA quiescent current
# ESP32 240Mhz without WiFi 41mA at 5V 
# ESP32 80Mhz 36mA at 5V (would be a saving of only 5mA)

# 3mA lightsleep mode
#   about 2mA ESP32-S3 plus leds
# 2mA deepsleep mode:
#   ESP32-S3 close to nothing
#   WS2812A Neopixel draws 0.6mA at 3.3V while off
#   Red led draws 0.6mA always
# Limitation: battery consumed during deepsleep mode is not accounted for.


# Battery low limit
_BATTERY_LOW_PERCENT = 90 # Percent

def _init():
    global _logger
    global _info # Public info about battery 
    global _volts_adc  # The ADC pin number to monitor 12V battery
    global _battery_task
    global _solenoid_watts
    global _heartbeat_task, _make_heartbeat
    
    _logger = getLogger(__name__)
    try:
        with open( config.BATTERY_JSON ) as file:
            _info = json.load( file )
    except Exception as e:
        _logger.info(f"init error loading json, rebuilding. {e}" )
        # Capacity and use in mAh
        _info = { # "capacity" : get that from config.json
            "use" : 0, # Wh
            "time" : 0, # time operating so far, in seconds
            "time_remaining": 0, # calculated time until battery is empty, seconds
            "low": False} # Indicator that battery is low
        _write_battery_info()
    # Copy this info from config.json to battery info at startup
    # Default to 50 Wh = 10000 mAh at 5V

    # This is the power consumed buy solenoids as 12V (voltage**2/resistance)
    # Default resistance 90 Ohms
    _solenoid_watts = 12*12/int( config.get_int("solenoid_resistance", 90 ) )
    _info["capacity"] = config.get_int( "battery_watt_hours", 50 )
    _battery_task = asyncio.create_task( _battery_process() )
    
    # Start with heartbeat
    _make_heartbeat = True
    _heartbeat_task = asyncio.create_task( _heartbeat_process() )


    _logger.debug("init ok")
    
async def _battery_process():
    
    while True:
        await asyncio.sleep( _UPDATE_EVERY_SECONDS )

        # Get time solenoids were "on", convert ms to seconds
        solenoid_time = solenoid.get_sum_msec_solenoids_on_and_zero()/1000
        # Accumulate energy use in Watt-hours, convert time from seconds to hours
        _info["use"] += (_ESP32_WATTS*_UPDATE_EVERY_SECONDS
                        + _solenoid_watts * solenoid_time )/3600
        
        # _UPDATE_EVERY_SECONDS is a good approximation of operating time, since
        # light sleep or deep sleep times will not be added. I think it's better
        # than using clock time time.ticks_ms().
        _info["time"] += _UPDATE_EVERY_SECONDS
        
        # Estimate remaining time
        if _info["use"] > 0:
            _info["time_remaining"] = (_info["time"] *
                (_info["capacity"]/_info["use"]) 
                - _info["time"]
                ) 
            _info["percent_used"] = _info["use"]/_info["capacity"]*100
        else:
            _info["time_remaining"] = 0 
            _info["percent_used"] = 0
        
        # A Very Simple Battery Low
        _info["low"] = _info["percent_used"] > _BATTERY_LOW_PERCENT

        # Update battery info on flash for the webserver to send to browser.
        # Be nice and ask for a time slice.
        async with scheduler.RequestSlice("battery", 200,
                    round(_UPDATE_EVERY_SECONDS*1000/2) ):
            _write_battery_info()
    
def _write_battery_info():
    with open( config.BATTERY_JSON, "w" ) as file:
        file.write( json.dumps( _info ) )

def set_to_zero():
    _logger.info(f"{_info=} now setting to zero")
    _info["use"] = 0
    _info["time"] = 0
    _info["time_remaining"] = 0
        
    _write_battery_info()
    
def get_info():
    return _info

async def _heartbeat_process():
    HEARTBEAT_INTERVAL = 5000
    HEARTBEAT_DURATION = 50
    from pinout import all_valid_midis
    from solenoid import note_on, note_off
    from random import randint
    while True:
        while True:
            # Leave at least one interval between playing and start
            await asyncio.sleep_ms( HEARTBEAT_INTERVAL )
            if not _make_heartbeat:
                break
            print(".", end="")
            midi_note = all_valid_midis[ randint( len(all_valid_midis) ) ]
            solenoid.note_on( midi_note )
            await asyncio.sleep_ms( HEARTBEAT_DURATION )
            solenoid.note_off( midi_note )
            
        while not _make_heartbeat:
            await asyncio.sleep_ms( HEARTBEAT_INTERVAL )

		
def start_battery_heartbeat():
    _make_heartbeat = True
	
def end_battery_heartbeat():
    _make_heartbeat = False
	
_init()
