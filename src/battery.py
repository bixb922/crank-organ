# (c) 20200 Hermann Paul von Borries
# MIT License
# Tallies battery usage

import asyncio
import time
import json
import os

from minilog import getLogger

from config import config
from led import led
from solenoid import solenoid
import scheduler
import fileops
from timezone import timezone
from matrix import Matrix, linear_regression

_UPDATE_EVERY_SECONDS = const(60)  # update readings every 60 seconds


# Battery low limit
_BATTERY_LOW_PERCENT = 10


class Battery:
    def __init__(
        self,
        battery_json_filename,
        battery_calibration_filename
    ):
        self.battery_json_filename = battery_json_filename
        self.battery_calibration_filename = battery_calibration_filename

        self.logger = getLogger(__name__)
        try:
            self.battery_info = fileops.read_json(self.battery_json_filename)
        except Exception as e:
            self.logger.info(f"init error loading json, rebuilding. {repr(e)}")
            self.battery_info = {}
        # Put missing information in battery_info, if necessary
        fallback = {
            "operating_seconds": 0,          # time operating (time with power on), in seconds 
            "playing_seconds": 0,  # time playing music, in seconds
            "remaining_seconds": 0,  # calculated time until battery is empty, seconds 
            "solenoid_on_seconds": 0,  # Time that solenoids were on, in seconds
            "percent_remaining": 100, # estimated with coefficients
            "tunes_played": 0,      # Number of tunes played
            "tunes_remaining": 0,   # Estimation of how many tunes can still be played with this battery charge
            "low": False,       # True/False, compares percent used with low battery level
            "date_zero": "0000-00-00", # Datetime when set to zero
        }
        for k, v in fallback.items():
            if k not in self.battery_info:
                self.battery_info[k] = v

        self.battery_task = asyncio.create_task(self._battery_process())

        # Start with heartbeat

        self.heartbeat_task = asyncio.create_task(self._heartbeat_process())

        self._write_battery_info()
        self.logger.debug("init ok")

    async def _battery_process(self):
        self.last_update = time.ticks_ms()
        await asyncio.sleep_ms(1000)
        # Calculate battery consumption coefficients, best fit
        self.get_coefficients()
        
        while True:
            await asyncio.sleep(_UPDATE_EVERY_SECONDS)
            self.update_calculations()

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
        #>>>> TEMPORARY CODE FOR CLEANUP OF BATTERY.JSON
        for k in ["use", "capacity", "time", "time_playing", "time_remaining", "solenoids_on", "solenoids_on_seconds", "percent_used"]:
            # It's "solenoid_on_seconds", without s
            try:
                del self.battery_info[k]
            except KeyError:
                pass
            
        fileops.write_json(
            self.battery_info, self.battery_json_filename, keep_backup=False
        )

    def set_to_zero(self):
        self.logger.info(f"{self.battery_info}, now setting to zero")
        self.battery_info["operating_seconds"] = 0
        self.battery_info["playing_seconds"] = 0
        self.battery_info["tunes_remaining"] = self.estimate_tunes_remaining()
        # No info of pace yet, estimate 4 minutes per tune
        self.battery_info["remaining_seconds"] = self.battery_info["tunes_remaining"] * 4*60
        self.battery_info["solenoid_on_seconds"] = 0
        self.battery_info["percent_remaining"] = 100
        self.battery_info["tunes_played"] = 0

        self.battery_info["low"] = False
        self.battery_info["date_zero"] = timezone.now_ymdhm()
        self.last_update = time.ticks_ms()
        self.update_calculations()

        self._write_battery_info()

    def update_calculations(self):
        now = time.ticks_ms()
        self.battery_info["operating_seconds"] += time.ticks_diff(now, self.last_update) / 1000
        # Get time solenoids were "on", convert ms to seconds
        self.battery_info["solenoid_on_seconds"] += solenoid.get_sum_msec_solenoids_on_and_zero() / 1000
        # Estimate remaining time and tunes
        self.battery_info["percent_remaining"] = self.estimate_percent_remaining()
        self.battery_info["tunes_remaining"] = self.estimate_tunes_remaining()
        percent_used = 100 - self.battery_info["percent_remaining"]

        # Extrapolate at current pace if at least tune played and some energy consumed.
        if percent_used > 0.5 and self.battery_info["tunes_played"] > 0:
            self.battery_info["remaining_seconds"] = (
                self.battery_info["operating_seconds"]/percent_used*100 )

        # A Very Simple Battery Low
        self.battery_info["low"] = (
            self.battery_info["percent_remaining"] < _BATTERY_LOW_PERCENT )
        self.last_update = now

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

    def end_of_tune(self, seconds):
        self.battery_info["playing_seconds"] += seconds
        self.battery_info["tunes_played"] += 1

    def record_level(self, level):
        # Level: 100=battery full
        #          0=battery empty
        #          reset=delete calibration, new calbration, new coefficients
        if "reset" in str(level):
            try:
                os.remove(self.battery_calibration_filename)
            except OSError:
                pass
            return
        level = int(level)
        if level < 0 or level > 100:
            raise ValueError
        try:
            bcj = self.read_calibration_data()
        except OSError:
            bcj = []
            
        bcj.append([ timezone.now_ymdhms(),
                  self.battery_info["operating_seconds"], 
                  self.battery_info["solenoid_on_seconds"], 
                  level,
                  self.battery_info["tunes_played"],
                  self.battery_info["playing_seconds"]])
        fileops.write_json(bcj, self.battery_calibration_filename, keep_backup=False)

      
    def read_calibration_data(self):
        try:
            bcj = fileops.read_json(self.battery_calibration_filename)
        except (OSError, ValueError):
            bcj = []
        for row in bcj:
            while len(row)<6:
                row.append(0)
        return bcj

    def get_coefficients(self):
        bcj = self.read_calibration_data()
        # xdata: first column must be all 1 to get beta[0]
        # Add x1=0, x2=0 y=100 as known point (i.e. with
        # no use, level is 100%)
        xdata = [[1],[0],[0]]
        ydata = [100]
        for _, operating_time, solenoid_on, level, _, _ in bcj:
            ydata.append( level )
            xdata[0].append( 1 )
            xdata[1].append( operating_time )
            xdata[2].append( solenoid_on  )
        X = Matrix().setElements( xdata )
        y = Matrix().setElements( [ydata] )
        self.coefficients =  linear_regression( X, y ).elements[0]


#        # >>>>Fit linear equation tunes = beta[0] + beta[1]*level
#        xdata = [[1],[100]]
#        ydata = [0]
#        for _, _, _, level, tunes, _ in bcj:
#            ydata.append( tunes )
#            xdata[0].append( 1 )
#            xdata[1].append( level )
#        X = Matrix().setElements( xdata )
#        y = Matrix().setElements( [ydata] )
#        beta =  linear_regression( X, y ).elements[0]
#        # Tune capacity occurs when battery level reaches 0
#        # so tune capacity is beta[0] + beta[1]*0 == beta[0]
#        self.tune_capacity = beta[0]
#        self.logger.debug(f"Coefficients calculated, level coefficients: {self.coefficients=}, tune capacity: {self.tune_capacity:.1f}")
        self.tune_capacity = 0
        if len(bcj) == 0:
            return
        
        # Get estimation for tune capacity of full battery using
        # the latest row in bcj, sort by operating seconds 
        #>>>Transition while there are elements with playing_seconds == 0
        bcj = [ row for row in bcj if row[5] != 0 ]
        bcj.sort(key=lambda x:x[2])
        print(f"get_coefficient {bcj[-1]=}")
        _, operating_seconds, solenoid_on_seconds, _, tunes_played, playing_seconds = bcj[-1]
        if tunes_played == 0:
            return
        # Calculate solenoid_on_seconds and playing_seconds average per tune:
        sos_per_tune = solenoid_on_seconds/tunes_played
        ps_per_tune = playing_seconds/tunes_played
        # Suppose for the estimation that the time between 
        # one tune and the next is 120 seconds
        sec_for_tune = ps_per_tune + 120

        # Estimate the number of tunes that can be played on full charge
        # by solving beta0 +beta1*sos_per_tune*tunes + beta2*sec_for_tune = 0
        beta = self.coefficients
        divisor = beta[1]*sos_per_tune + beta[2]*sec_for_tune
        if divisor == 0:
            return
        self.tune_capacity = -beta[0]/divisor
        
        self.logger.debug(f"Coefficients calculated: {self.coefficients=}, tune capacity: {self.tune_capacity}")

    def estimate_percent_remaining(self):
        beta = self.coefficients
        estimate = (beta[0] 
                    + beta[1]*self.battery_info["operating_seconds"] 
                    + beta[2]*self.battery_info["solenoid_on_seconds"])
        return max(min(estimate,100),0)
    
    def estimate_tunes_remaining(self):
        # Must be called after updating self.battery_info["percent_remaining"]
        return self.tune_capacity*self.battery_info["percent_remaining"]/100

    
battery = Battery(
    config.BATTERY_JSON,
    config.BATTERY_CALIBRATION_JSON,
)
