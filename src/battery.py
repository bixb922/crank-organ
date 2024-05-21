# (c) 20200 Hermann Paul von Borries
# MIT License
# Tallies battery usage


# >>> see battery off problem.


import asyncio
import time
import os

from minilog import getLogger

from config import config
from led import led
from solenoid import solenoid
import scheduler
import fileops
from tachometer import crank
from timezone import timezone
from matrix import Matrix, linear_regression

# update readings every 60 seconds
_UPDATE_EVERY_SECONDS = const(60)  # type:ignore


# Battery low limit
_BATTERY_LOW_PERCENT = const(10) # type:ignore

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
            "solenoid_on_seconds": 0,  # Time that solenoids were on, in seconds
            "tunes_played": 0,      # Number of tunes played
            "date_zero": "0000-00-00", # Datetime when set to zero
            # These magnitudes are estimated:
            "remaining_seconds": None,  # calculated time until battery is empty, seconds 
            "percent_remaining": None, # estimated with coefficients
            "tunes_remaining": None,   # Estimation of how many tunes can still be played with this battery charge
            "low": None,       # True/False, compares percent used with low battery level
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

            await asyncio.sleep(_UPDATE_EVERY_SECONDS)

    def _write_battery_info(self)->None:
        fileops.write_json(
            self.battery_info, self.battery_json_filename, keep_backup=False
        )

    def set_to_zero(self)->None:
        self.logger.info(f"{self.battery_info}, now setting to zero")
        self.battery_info["operating_seconds"] = 0
        self.battery_info["playing_seconds"] = 0
        self.battery_info["solenoid_on_seconds"] = 0
        self.battery_info["tunes_played"] = 0

        self.battery_info["percent_remaining"] = None
        self.battery_info["tunes_remaining"] = None
        self.battery_info["remaining_seconds"] = None
        self.battery_info["low"] = None
        self.battery_info["date_zero"] = timezone.now_ymdhm()
        self.last_update = time.ticks_ms()
        self.update_calculations()

        self._write_battery_info()

    def update_calculations(self)->None:
        now = time.ticks_ms()
        self.battery_info["operating_seconds"] += time.ticks_diff(now, self.last_update) / 1000
        # Get time solenoids were "on", convert ms to seconds
        self.battery_info["solenoid_on_seconds"] += solenoid.get_sum_msec_solenoids_on_and_zero() / 1000
        
        # Estimate remaining time and tunes
        self.battery_info["percent_remaining"] = self.estimate_percent_remaining()
        self.battery_info["tunes_remaining"] = self.estimate_tunes_remaining()
        self.battery_info["remaining_seconds"] = self.estimate_operating_seconds_remaining()
        self.battery_info["low"] = self.estimate_low()
        self.last_update = now

    def get_info(self)->dict:
        return self.battery_info

    async def _heartbeat_process(self)->None:
        heartbeat_period = config.get_int("battery_heartbeat_period", 0)
        heartbeat_duration = config.get_int("battery_heartbeat_duration", 0)
        if heartbeat_period == 0 or heartbeat_duration == 0:
            return

        self.make_heartbeat = True

        await asyncio.sleep_ms(heartbeat_period)
        from solenoid import solenoid

        while True:
            while self.make_heartbeat:
                # Don't play heartbeat if crank is turning
                # If crank not installed: heartbeat always
                # If crank is installed: heartbeat only when crank not turning
                if not crank.is_installed() or (crank.is_installed() and not crank.is_turning()):
                    print(".", end="")
                    led.heartbeat()
                    await solenoid.play_random_note(heartbeat_duration)
                    self.logger.debug(f"Playing random note for {heartbeat_duration=}")
                await asyncio.sleep_ms(heartbeat_period)

            while not self.make_heartbeat:
                await asyncio.sleep_ms(heartbeat_period)
            # Wait a bit before starting
            await asyncio.sleep_ms(heartbeat_period)

    def start_heartbeat(self)->None:
        self.make_heartbeat = True

    def end_heartbeat(self)->None:
        self.make_heartbeat = False

    def end_of_tune(self, seconds)->None:
        self.battery_info["playing_seconds"] += seconds
        self.battery_info["tunes_played"] += 1

    def record_level(self, level)->None:
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

      
    def read_calibration_data(self)->dict:
        try:
            bcj = fileops.read_json(self.battery_calibration_filename)
        except (OSError, ValueError):
            bcj = []

        return bcj

    def get_coefficients(self)->None:
        # Start with some defaults

        self.calibrated = False
        bcj = self.read_calibration_data()
        if len(bcj) == 0:
            self.logger.debug("Can't calibrate: no calibration data")
            return
        
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
        # Force "battery full" level to 100
        # If it's outside this range, then the estimation is not
        # very good
        if 95 <= self.coefficients[0] <= 105:
            self.coefficients[0] = 100
        else:
            self.logger.info("Estimation coefficient[0] is not near 100, battery usage prediction may be off")
        
        # Get estimation for tune capacity of full battery using
        # the latest row in bcj, sort by operating seconds 
        tunes_played = 0
        bcj.sort(key=lambda x:x[2])
        _, _, solenoid_on_seconds, _, tunes_played, playing_seconds = bcj[-1]
        if tunes_played == 0:
            self.logger.debug("Can't calibrate: tunes played == 0")
            return
        # Calculate solenoid_on_seconds and playing_seconds average per tune:
        sos_per_tune = solenoid_on_seconds/tunes_played
        self.seconds_per_tune = playing_seconds/tunes_played
        # Suppose for the estimation that the time between 
        # one tune and the next is 120 seconds
        sec_for_tune = self.seconds_per_tune + 120

        # Estimate the number of tunes that can be played on full charge
        # by solving beta0 +beta1*sos_per_tune*tunes + beta2*sec_for_tune = 0
        beta = self.coefficients
        divisor = beta[1]*sos_per_tune + beta[2]*sec_for_tune
        if divisor == 0:
            self.logger.debug("Can't calibrate: divisor == 0")
            return
        self.tune_capacity = -beta[0]/divisor
        self.calibrated = True
        self.logger.debug(f"Calibration coefficients: {self.coefficients=}, tune capacity: {self.tune_capacity}")

    def estimate_percent_remaining(self)->None|float:
        if self.calibrated:
            beta = self.coefficients
            estimate = (beta[0] 
                        + beta[1]*self.battery_info["operating_seconds"] 
                        + beta[2]*self.battery_info["solenoid_on_seconds"])
            return max(min(estimate,100),0)
    
    def estimate_tunes_remaining(self)->None|float:
        if self.calibrated:
            # Must be called after updating self.battery_info["percent_remaining"]
            return self.tune_capacity*self.battery_info["percent_remaining"]/100

    def estimate_operating_seconds_remaining(self)->None|float:
        if self.calibrated:
            # Estimate average time a tune takes, including the
            # pause between tunes.
            if self.battery_info["tunes_played"] <= 3:
                # If few tunes since battery zero: 
                # estimate 2 minutes between tunes.
                total_per_tune = self.seconds_per_tune + 120
            else:
                # If many tunes already played with this
                # battery charge, estimate time based on current use
                total_per_tune = self.battery_info["operating_seconds"]/self.battery_info["tunes_played"]
            return self.estimate_tunes_remaining()*total_per_tune
    
    def estimate_low(self)->None|bool:
        if self.calibrated:
            return self.estimate_percent_remaining() < _BATTERY_LOW_PERCENT

battery = Battery(
    config.BATTERY_JSON,
    config.BATTERY_CALIBRATION_JSON,
)
