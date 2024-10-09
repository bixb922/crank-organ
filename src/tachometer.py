
# (c) 2023 Hermann Paul von Borries
# MIT License
# Crank rotation speed sensor. Still in testing phase.
import asyncio
from time import ticks_ms, ticks_diff

from machine import Pin

if __name__ == "__main__":
    # >>> for debug
    import sys
    sys.path.append("software/mpy")
    
from minilog import getLogger
from pinout import gpio
from config import config
from counter import Encoder, Counter

# Number of pulses (1 pulse = off + on) per revolution
PULSES_PER_REV = config.get_int("pulses_per_revolution", 24) 

# Factor to convert the milliseconds  to revolutions per second (rpsec)
# and vice-versa. rpsec = FACTOR/msec, msec = FACTOR/rpsec
FACTOR = 1000/PULSES_PER_REV

# Less than these minimum means "stopped" or "not turning"
# The two values give the detection a hysteresis.
LOWER_THRESHOLD_RPSEC = config.get_float( "lower_threshold_rpsec", 0.3)
HIGHER_THRESHOLD_RPSEC = config.get_float( "higher_threshold_rpsec", 0.7) # greater than this value means the crank is *turning*

# "Normal" turning speed, when MIDI speed == real speed
NORMAL_RPSEC = config.get_float( "normal_rpsec", 1.2)


import pcnt
class TachoDriver:
    def __init__(self,tachometer_pin, automatic_playback):
        self.logger = getLogger(__name__)
        self.counter_task = None
        self.rpsec = 0
        self.counter = None

        if not tachometer_pin or automatic_playback:
            self.logger.debug("Crank sensor not in configuration")
            return
        # >>> may be necessary to implement Encoder too
        # >>> but needs a second pin.
        # >>> check if Encoder needs filter_ns
        self.counter = Counter( 0, 
                               Pin( tachometer_pin, Pin.IN, Pin.PULL_UP ), 
                               direction=Counter.UP,
                               edge=Counter.RISING+Counter.FALLING,
                               filter_ns=20_000)
        self.counter_task = asyncio.create_task( self._sensor_process() )
        self.logger.info("init ok")

    async def _sensor_process( self ):
        last_time = ticks_ms()
        last_pulse_count = self.counter.value()
        
        samples = []           
        while True:
            await asyncio.sleep_ms(300)
            new_time = ticks_ms()
            new_pulse_count =  self.counter.value()
            # Compute differences to get revolutions per second
            time_ms = ticks_diff( new_time, last_time )
            pulses = new_pulse_count - last_pulse_count
            rpsec = (pulses/PULSES_PER_REV)/(time_ms/1000)
            if PULSES_PER_REV < 20:
                # Use samples only when few pulses per revolution
                samples.append( rpsec )
                if len(samples) > PULSES_PER_REV/2:
                    samples.pop(0)
                self.rpsec = sum(samples)/len(samples)
            else:
                self.rpsec = rpsec
            last_pulse_count = new_pulse_count
            last_time = new_time

    def get_rpsec( self ):
        return self.rpsec

    def is_installed(self):
        return bool(self.counter)

    def irq_report( self ):
        # This function prepares data for graph on diag.html
        # page
        async def _report_process( ):
            while True:
                await asyncio.sleep_ms(250)
                self.report_rps.append( self.get_rpsec() )
                self.report_times.append( ticks_ms() )
                self.report_rps = self.report_rps[-20:]
                self.report_times = self.report_times[-20:]

        if not self.is_installed():
            return
        # TachoDriver report for webserver/web page
        if not hasattr(self,"report_task"):
            self.report_rps = []
            self.report_times = [] # X axis
            self.report_task = asyncio.create_task( _report_process() )
        times = [] # used as X axis in graph
        if len(self.report_times)>0:
            t0 = self.report_times[0] # 0.0 to 1.0
            times = [ round(ticks_diff(x,t0)/1000,1) for x in self.report_times ]
        return {
            "dtList": [],
            "ms_since_last_irq": 0,
            "rpsecList": self.report_rps,
            "timesList": times,
            "now": ticks_ms(),
            "is_installed": self.is_installed(),
            "lower_threshold_rpsec": LOWER_THRESHOLD_RPSEC,
            "higher_threshold_rpsec": HIGHER_THRESHOLD_RPSEC,
            "normal_rpsec": NORMAL_RPSEC
        }

class Crank:
    # Trigger events based on the crank revolution speed
    # like start and stop turning
    def __init__(self,tachometer_pin,automatic_playback):
        self.logger = getLogger(__name__)

        # Set UI setting of velocity to 50, halfway from 0 to 100.
        self.set_velocity(50)
        # Initialize tachometer driver
        self.td = TachoDriver(tachometer_pin,automatic_playback)
        
        # Dictionary of events to be fired
        self.events={}
        # Register at least one event to prevent max from failing
        self.register_event(0)

        # At startup crank is not turning 
        self.crank_is_turning = False

        # A task to monitor the crank and generate the events
        self.crank_monitor_task = asyncio.create_task(self._crank_monitor_process())
        self.logger.debug("crank init ok")
        
    def register_event(self,when_ms)->asyncio.Event:
        # Can register one event for each time only.
        # Return event if registered
        return self.events.setdefault( when_ms, asyncio.Event())

    async def _crank_monitor_process(self):
        if not self.is_installed():
            return
        # This code connects the tachometer sensor with the event that
        # starts a new tune in setlist
        # Turning hasn't started
        time_when_turning_started = None
        
        # Calculate a time lapse to wait for rpsec to stabilize
        some_pulses = int(4*HIGHER_THRESHOLD_RPSEC/PULSES_PER_REV)+1
        while True:
            self.crank_is_turning = False
            # Wait for crank to start turning
            while self.td.get_rpsec()<HIGHER_THRESHOLD_RPSEC:
                await asyncio.sleep_ms(50)

            self.logger.debug("---------> Crank now turning")    
            # Guard against spurious events, wait for some pulses
            await asyncio.sleep_ms(some_pulses)
            
            time_when_turning_started = ticks_ms()
            self.crank_is_turning = True
            # Check until all registered events have been triggered and some
            max_time_to_monitor = max(w for w in self.events.keys())+1000
            while self.td.get_rpsec()>LOWER_THRESHOLD_RPSEC:
                await asyncio.sleep_ms(100) 
                time_since_start = ticks_diff(ticks_ms(),time_when_turning_started)
                #print(f"crank is turning {self.td.get_rpsec()=}, processing events, time left {max_time_to_monitor-time_since_start} msec {time_since_start=} {max_time_to_monitor=}" )
                for when_ms,ev in self.events.items():
                    if time_since_start>=when_ms and not ev.is_set():
                        self.logger.debug(f"---------> rpsec crank turning - set event at {when_ms=} {self.td.get_rpsec()=}")
                        ev.set()
                        
                if time_since_start>max_time_to_monitor:
                    # Save some CPU, don't continue to monitor crank turning
                    # until turning stops. All events have been generated
                    break
                    
            # Wait until crank stops turning
            while self.td.get_rpsec()>LOWER_THRESHOLD_RPSEC:
                await asyncio.sleep_ms(100)
                #print(f"crank is turning {self.td.get_rpsec()=}" )
            
            # Record that crank is not turning
            self.crank_is_turning = False
            self.logger.debug(f"---------> Crank now stopped {self.td.get_rpsec()=}")
            
    def is_turning(self):
        return self.crank_is_turning 

    async def wait_stop_turning(self):
        if self.is_installed():
            while True:
                if not self.is_turning():
                    return
                await asyncio.sleep_ms(100)
        # If not installed, no waiting.
    

    def is_installed(self):
        return self.td.is_installed()

    def get_normalized_rpsec(self, tempo_follows_crank ):
        # Used in player.py to delay/hasten music
        # depending on crank speed AND UI setting
        # If no crank, UI can still change tempo!
        if tempo_follows_crank:
            return self.td.get_rpsec() / NORMAL_RPSEC * self.tempo_multiplier 
        return self.tempo_multiplier 

    def set_velocity_relative( self, change):
        # Change velocity settings relative to current setting
        ui_vel = min(max(self.ui_velocity+change,0),100)
        self.set_velocity( ui_vel )

    def set_velocity(self,ui_vel):
        # Velocity is a superimposed manual control via UI to alter the "normal"
        # playback speed. Crank._ui_velocity is the velocity as set by the ui
        # (50=normal, 0=lowest, 100=highest).

        self.ui_velocity = ui_vel
        # The UI sets _ui_velocity to a value from 0 and 100, normal=50.
        # For easier use this value from 0 to 100 is changed
        # to a multiplier for the MIDI tempo from 0.5 to 2
        # (half tempo to double tempo).
        # tempo_multiplier is a multiplier, 1=normal, 2=double speed, 0.5=half speed
        # f(0) => 0.5
        # f(50) => 1
        # f(100) => 2
        # Calculate the multiplier needed by get_normalized_rpsec
        self.tempo_multiplier = ui_vel * ui_vel / 10000 + ui_vel / 200 + 0.5

    def complement_progress(self,progress):
        # Add crank information to progress, to be sent to the browser.
        progress["velocity"] = self.ui_velocity
        progress["rpsec"] = self.td.get_rpsec()
        progress["is_turning"] = self.is_turning()
        progress["tacho_installed"] = self.is_installed()
        progress["tempo_multiplier"] = self.tempo_multiplier
        return progress

# Rotary encoder to detect tempo
# This is a potentiometer type rotary encoder,
# not the crank revolution sensor.
class TempoEncoder:
    def __init__( self ):
        self.logger = getLogger("TempoEncoder")
        self.tempo_task = asyncio.create_task( self._tempo_process )
        
    async def _tempo_process(self):
        await asyncio.sleep_ms(10) # Let general startup finish
        rotary_tempo_mult = config.get("rotary_tempo_mult", 1)
        if gpio.tempo_a and gpio.tempo_b and gpio.switch:
            encoder_a = Pin( gpio.tempo_a, Pin.IN, Pin.PULL_UP )
            encoder_b = Pin( gpio.tempo_a, Pin.IN, Pin.PULL_UP )
            switch = Pin( gpio.switch, Pin.IN, Pin.PULL_UP )
            encoder = Encoder( 1, filter_ns=13000, # Highest value possible
                               phase_a=encoder_a, 
                               phase_b=encoder_b, 
                               phases=2)
        else:
            self.logger.info( "No rotary encoder defined")
            return
        while True:
            # Set velocity about 10 times a second following pulse counter
            await asyncio.sleep_ms(100)
            if switch.value() == 0:
                crank.set_velocity(50)
            if (v := encoder.value()):
                crank.set_velocity_relative( v * rotary_tempo_mult )       


crank = Crank(gpio.tachometer_pin,config.get_int("automatic_delay", 0))

