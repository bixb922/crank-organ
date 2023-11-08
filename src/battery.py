# (c) 2023 Hermann Paul von Borries
# MIT License
# Tallies battery usage
import asyncio
import json
import time

from minilog import getLogger

from config import config
from solenoid import solenoid
import scheduler
import fileops

_UPDATE_EVERY_SECONDS = const(60) # update readings every 60 seconds

# ESP32 power consumption = 0.053*5/0.9 # 54mA at 5V. Efficiency of DC-DC conversion 90%
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

class Battery():
    def __init__( self, battery_json_filename, solenoid_watts, fixed_watts, battery_watt_hours ):
        self.battery_json_filename = battery_json_filename
        self.solenoid_watts = solenoid_watts
        self.fixed_watts = fixed_watts
        self.battery_watt_hours = battery_watt_hours
        
        self.logger = getLogger(__name__)
        try:
            self.battery_info = fileops.read_json( self.battery_json_filename )
        except Exception as e:
            self.logger.info(f"init error loading json, rebuilding. {e}" )
            self.battery_info = {}
        # Put missing information in battery_info, if necessary
        fallback = { 
                "use" : 0, # Wh
                "time" : 0, # time operating so far, in seconds
                "time_remaining": 0, # calculated time until battery is empty, seconds
                "low": False,
				"percent_used": 0,
				"capacity": 0
				}
        for k,v in fallback.items(): 
            if k not in self.battery_info:
                self.battery_info[k] = v
                
        # refresh battery capacity every reboot
        self.battery_info["capacity"] = self.battery_watt_hours
        self.battery_task = asyncio.create_task( self._battery_process() )

        # Start with heartbeat
        self.make_heartbeat = True
        self.heartbeat_task = asyncio.create_task(
                self._heartbeat_process() )

        self._write_battery_info()
        self.logger.debug("init ok")

    async def _battery_process( self ):
        last_update = time.ticks_ms()
        while True:
            await asyncio.sleep( _UPDATE_EVERY_SECONDS )

            # Get time solenoids were "on", convert ms to seconds
            solenoid_time = solenoid.get_sum_msec_solenoids_on_and_zero()/1000
            # Accumulate energy use in Watt-hours, convert time from seconds to hours
            now = time.ticks_ms()
            time_diff = time.ticks_diff( now, last_update )/1000
            last_update = now
            # Times in seconds
            # Calculate use in watt-hours, same units as
            # battery capacity
            self.battery_info["use"] += ( 
                self.fixed_watts * time_diff
                + self.solenoid_watts * solenoid_time )/3600

            self.battery_info["time"] += time_diff

            # Estimate remaining time
            if self.battery_info["use"] > 0:
                self.battery_info["time_remaining"] = (self.battery_info["time"] *
                    (self.battery_watt_hours/self.battery_info["use"]) 
                    - self.battery_info["time"]
                    ) 
                self.battery_info["percent_used"] = self.battery_info["use"]/self.battery_watt_hours*100
            else:
                self.battery_info["time_remaining"] = 0 
                self.battery_info["percent_used"] = 0

            # A Very Simple Battery Low
            self.battery_info["low"] = (
				self.battery_info["percent_used"] > _BATTERY_LOW_PERCENT
			)

            # Update battery info on flash for the webserver to send to browser.
            # Be nice and ask for a time slice.
            try:
                async with scheduler.RequestSlice("battery", 200, 10_000 ):
                    self._write_battery_info( )
            except RuntimeError:
                # Try writing next time
                pass

    def _write_battery_info( self ):
        fileops.write_json( self.battery_info,
                           self.battery_json_filename, 
                           keep_backup=False )

    def set_to_zero( self ):
        self.logger.info(f"{self.battery_info}, now setting to zero")
        self.battery_info["use"] = 0
        self.battery_info["time"] = 0
        self.battery_info["time_remaining"] = 0
        self.battery_info["low"] = False

        self._write_battery_info()

    def get_info( self ):
        return self.battery_info

    async def _heartbeat_process( self ):
        from solenoid import solenoid
        
        HEARTBEAT_INTERVAL = 5000
        HEARTBEAT_DURATION = 100
        

        while True:
            while self.make_heartbeat:
                #>>> change if resistor installed
                # >>> debug?
                print(".", end="")
                solenoid.play_random_note(
                    HEARTBEAT_DURATION )
                await asyncio.sleep_ms( HEARTBEAT_INTERVAL )


            while not self.make_heartbeat:
                await asyncio.sleep_ms( HEARTBEAT_INTERVAL )
            # Wait a bit before starting
            await asyncio.sleep_ms( HEARTBEAT_INTERVAL )


    def start_battery_heartbeat( self ):
        print(">>> start battery heartbeat")
        self.make_heartbeat = True

    def end_battery_heartbeat( self ):
        print(">>> end battery heartbeat")
        self.make_heartbeat = False


battery = Battery(config.BATTERY_JSON, 
                 config.get_float("solenoid_watts", 1.6 ),
                 config.get_float("fixed_watts", 0.6 ),
                 config.get_int( "battery_watt_hours", 50 )
                 )
