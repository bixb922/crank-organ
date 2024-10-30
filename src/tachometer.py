
# (c) 2023 Hermann Paul von Borries
# MIT License
# Crank rotation speed sensor. Still in testing phase.
import asyncio
from time import ticks_ms, ticks_diff
from machine import Pin

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


class TachoDriver:
    def __init__(self,tachometer_pin1, tachometer_pin2, automatic_playback):
        self.logger = getLogger(__name__)
        self.counter_task = None
        self.rpsec = 0
        if not tachometer_pin1 or automatic_playback:
            self.logger.debug("Crank sensor not configured")
            return
        
        if tachometer_pin1 and not tachometer_pin2:
            # One pin defined means: simple counter for crank
            counter = Counter( 0, 
                    Pin( tachometer_pin1, Pin.IN, Pin.PULL_UP ), 
                    direction=Counter.UP,
                    edge=Counter.RISING+Counter.FALLING,
                    filter_ns=20_000) # Highest filter value possible
        else:
            # Two pins defined means: rotary encoder for crank
            counter = Encoder( 0,
                    phase_a=Pin( tachometer_pin1, Pin.IN, Pin.PULL_UP ), 
                    phase_b=Pin( tachometer_pin2, Pin.IN, Pin.PULL_UP ), 
                    phases=1, # Can be 2 or 4 too, but not much advantage in this case.
                    filter_ns=20_000) # Highest filter value possible
            
        self.counter_task = asyncio.create_task( self._sensor_process(counter) )
        self.logger.info("init ok")

    async def _sensor_process( self, counter ):
        # Prime the loop
        last_time = ticks_ms()
        counter.value(0)
        while True:
            await asyncio.sleep_ms(200)
            # Get pulses since last call, i.e. value(0) resets
            # the counter to 0. 
            # Take abs() because if a Encoder is present, value
            # can be negative if crank is turned in the opposite
            # direction. Using abs() neither the order of the pins
            # nor the direction of rotation matters
            # If there is a Counter, value() will aways be positive anyhow.
            pulses =  abs(counter.value(0))
            new_time = ticks_ms()
            time_ms = ticks_diff( new_time, last_time )
            # time_ms should never be 0, because there is a sleep_ms in this loop
            self.rpsec = (pulses/PULSES_PER_REV)/(time_ms/1000)
            last_time = new_time

    def get_rpsec( self ):
        return self.rpsec

    def is_installed(self):
        return bool(self.counter_task)

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
    def __init__(self,tachometer_pin1, tachometer_pin2,automatic_playback):
        self.logger = getLogger(__name__)

        # Set UI setting of velocity to 50, halfway from 0 to 100.
        self.set_velocity(50)
        # Initialize tachometer driver
        self.td = TachoDriver(tachometer_pin1, tachometer_pin2,automatic_playback)
        
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
        # TempoEncoder can also set this velocity. Both are coordinated.

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
    def __init__( self, tempo_a, tempo_b, tempo_switch, rotary_tempo_mult ):
        self.logger = getLogger("TempoEncoder")
        if not tempo_a or not tempo_b or not tempo_switch:
            self.logger.debug("TempoEncoder not connected")
            return
        switch = Pin( tempo_switch, Pin.IN, Pin.PULL_UP )
        encoder = Encoder( 1, filter_ns=13000, # Highest value possible
                            phase_a=Pin( tempo_a, Pin.IN, Pin.PULL_UP ), 
                            phase_b=Pin( tempo_b, Pin.IN, Pin.PULL_UP ), 
                            phases=1)
        switch = Pin( tempo_switch, Pin.IN, Pin.PULL_UP )
        self.tempo_task = asyncio.create_task( self._tempo_process( encoder, switch, rotary_tempo_mult ) )
        self.logger.info("init done")

    async def _tempo_process(self, encoder, switch, rotary_tempo_mult ):
        encoder.value(0)
        times_switch_down = 0
        while True:
            # Read velocity about 10 times a second 
            await asyncio.sleep_ms(100)
            # Read pulses since last read, reset counter to 0.
            if (v := encoder.value(0)):
                crank.set_velocity_relative( v * rotary_tempo_mult ) 
                # Reset "switch pressed" counter 
                # because on some devices the switch closes intermittently during
                # rotation without pressing the switch.
                times_switch_down = 0  
                continue   
            # Switch is "normal on": pressed gives .value()==0
            if switch.value():
                # Switch is off
                times_switch_down = 0
            else:
                # Count times switch on
                times_switch_down += 1
            # Was this a long press? i.e. about half a second?           
            if times_switch_down >= 4:
                # Button on rotary encoder pressed, reset velocity to normal
                crank.set_velocity(50)
                times_switch_down = 0


# Player/setlist need to know if crank is turning.
crank = Crank(gpio.tachometer_pin1, gpio.tachometer_pin2, config.get_int("automatic_delay", 0))

# The tempo encoder operates as a independent task,
# no further calls necessary.
_tempo_encoder = TempoEncoder( gpio.tempo_a, gpio.tempo_b, gpio.tempo_switch, config.cfg.get("rotary_tempo_mult", 1) )

