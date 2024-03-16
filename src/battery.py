# (c) 20200 Hermann Paul von Borries
# MIT License
# Tallies battery usage
import asyncio
import time

from minilog import getLogger

from config import config
from led import led
from solenoid import solenoid
import scheduler
import fileops
from timezone import timezone

_UPDATE_EVERY_SECONDS = const(60)  # update readings every 60 seconds

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
_BATTERY_LOW_PERCENT = 90  # Percent


class Battery:
    def __init__(
        self,
        battery_json_filename,
        solenoid_watts,
        fixed_watts,
        battery_watt_hours,
    ):
        self.battery_json_filename = battery_json_filename
        self.solenoid_watts = solenoid_watts
        self.fixed_watts = fixed_watts
        self.battery_watt_hours = battery_watt_hours

        self.logger = getLogger(__name__)
        try:
            self.battery_info = fileops.read_json(self.battery_json_filename)
        except Exception as e:
            self.logger.info(f"init error loading json, rebuilding. {repr(e)}")
            self.battery_info = {}
        # Put missing information in battery_info, if necessary
        fallback = {
            "use": 0,  # Wh
            "time": 0,  # time operating so far, in seconds
            "time_playing": 0,
            "time_remaining": 0,  # calculated time until battery is empty, seconds
            "low": False,
            "percent_used": 0,
            "capacity": 0,
            "solenoids_on": 0,
            "date_zero": "0000-00-00",
        }
        for k, v in fallback.items():
            if k not in self.battery_info:
                self.battery_info[k] = v

        # refresh battery capacity every reboot
        self.battery_info["capacity"] = self.battery_watt_hours

        self.battery_task = asyncio.create_task(self._battery_process())

        # Start with heartbeat

        self.heartbeat_task = asyncio.create_task(self._heartbeat_process())

        self._write_battery_info()
        self.logger.debug("init ok")

    async def _battery_process(self):
        last_update = time.ticks_ms()
        while True:
            await asyncio.sleep(_UPDATE_EVERY_SECONDS)

            # Get time solenoids were "on", convert ms to seconds
            solenoid_time = solenoid.get_sum_msec_solenoids_on_and_zero() / 1000
            # Times in battery_info in seconds
            self.battery_info["solenoids_on"] += solenoid_time

            # Get time elapsed
            now = time.ticks_ms()
            time_diff = time.ticks_diff(now, last_update) / 1000
            last_update = now
            # Calculate use in watt-hours, same units as
            # battery capacity
            self.battery_info["use"] += (
                self.fixed_watts * time_diff
                + self.solenoid_watts * solenoid_time
            ) / 3600
            self.battery_info["time"] += time_diff

            # Estimate remaining time
            if self.battery_info["use"] > 0:
                self.battery_info["time_remaining"] = (
                    self.battery_info["time"]
                    * (self.battery_watt_hours / self.battery_info["use"])
                    - self.battery_info["time"]
                )
                self.battery_info["percent_used"] = (
                    self.battery_info["use"] / self.battery_watt_hours * 100
                )
            else:
                self.battery_info["time_remaining"] = 0
                self.battery_info["percent_used"] = 0

            # A Very Simple Battery Low
            self.battery_info["low"] = (
                self.battery_info["percent_used"] > _BATTERY_LOW_PERCENT
            )

            # Update battery info on flash to keep tally
            # of usage. The webserver does not read this file,
            # but uses get_info() from memory.
            # Be nice and ask for a time slice. Updating a file
            # in flash usually takes 20 or 30 msec but may go up to 190 msec
            try:
                async with scheduler.RequestSlice("battery", 200, 10_000):
                    self._write_battery_info()
            except RuntimeError:
                # Music playback did not have a pause
                # Try writing next time
                pass

    def _write_battery_info(self):
        fileops.write_json(
            self.battery_info, self.battery_json_filename, keep_backup=False
        )

    def set_to_zero(self):
        self.logger.info(f"{self.battery_info}, now setting to zero")
        self.battery_info["use"] = 0
        self.battery_info["time"] = 0
        self.battery_info["time_remaining"] = 0
        self.battery_info["time_playing"] = 0
        self.battery_info["low"] = False
        self.battery_info["percent_used"] = 0
        self.battery_info["solenoids_on"] = 0
        self.battery_info["date_zero"] = timezone.now_ymdhm()
        self._write_battery_info()

    def get_info(self):
        return self.battery_info

    async def _heartbeat_process(self):
        heartbeat_period = config.get_int("battery_heartbeat_period", 0)
        heartbeat_duration = config.get_int("battery_heartbeat_duration", 0)
        if heartbeat_period == 0 or heartbeat_duration == 0:
            return

        self.make_heartbeat = True

        await asyncio.sleep_ms(heartbeat_period)
        from solenoid import solenoid

        while True:
            while self.make_heartbeat:
                print(".", end="")
                led.heartbeat()
                await solenoid.play_random_note(heartbeat_duration)
                await asyncio.sleep_ms(heartbeat_period)

            while not self.make_heartbeat:
                await asyncio.sleep_ms(heartbeat_period)
            # Wait a bit before starting
            await asyncio.sleep_ms(heartbeat_period)

    def start_heartbeat(self):
        self.make_heartbeat = True

    def end_heartbeat(self):
        self.make_heartbeat = False

    def add_msec_playing(self, seconds):
        self.battery_info["time_playing"] += seconds


battery = Battery(
    config.BATTERY_JSON,
    config.get_float("solenoid_watts", 1.6),
    config.get_float("fixed_watts", 0.6),
    config.get_int("battery_watt_hours", 50),
)
