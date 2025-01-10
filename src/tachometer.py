
# (c) 2023 Hermann Paul von Borries
# MIT License
# Crank rotation speed sensor. Still in testing phase.
import asyncio
from time import ticks_ms, ticks_diff
from machine import Pin

from minilog import getLogger
from drehorgel import config
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

class LowPassFilter:
    def __init__( self, fc, step ):
        # Time constant of low pass filter is 
        # 1/(2*pi*cutoff frequency)
        rc = 1/(6.28*fc)
        self.alpha = step/(rc+step)
        self.current = 0

    def filter( self, rpsec ):
        if rpsec >= HIGHER_THRESHOLD_RPSEC:
            self.current = rpsec*self.alpha + self.current*(1-self.alpha)
        else:
            self.current = rpsec
        return self.current
    # FIlter probably would be more precise calculating
    # alpha in filter() with the real step instead of a
    # estimated step

# This is the low level driver for the crank rotation sensor
# Main output is get_rps() which returns the "rotations per second"
# of the crank.
class TachoDriver:
    def __init__(self, tachometer_pin1, tachometer_pin2):
        self.logger = getLogger(__name__)
        self.counter_task = None
        self.rpsec = 0
        self.encoder_factor = 1 # Encoder phases compensation
        if not tachometer_pin1 or config.get_int("automatic_delay", 0):
            self.logger.debug("Crank sensor not enabled")
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
                    phases=2, # For a nominal 200 stripes this will count 400 pulses
                    filter_ns=20_000) # Highest filter value possible
            self.encoder_factor = 2 # To compensate fo r phases=2
        
        # For diag.html report of crank frequencies
        self.report_rps = []
        self.report_times = []
        
        # Start the sensor process
        self.counter_task = asyncio.create_task( self._sensor_process(counter) )
        self.logger.info("init ok")

    async def _sensor_process( self, counter ):
        # Prime the loop
        last_time = ticks_ms()
        counter.value(0) # Reset value counter to 0
        step = 100 # Delay between 2 reads of the crank
        # Most crank variations occur at the crank rev/sec frequency
        # Filter whatever is faster than that.
        # If fc were set to 0, that disables the crank altogether
        # Prevent setting fc to 0
        fc = max( 0.2, config.get_float("crank_lowpass_cutoff", NORMAL_RPSEC ))
        
        lpf = LowPassFilter( fc,  step/1_000 )
    
        while True:
            await asyncio.sleep_ms(step)
            # Get pulses since last call, i.e. value(0) resets
            # the counter to 0. 
            # Take abs() because if a Encoder is present, value
            # can be negative if crank is turned in the opposite
            # direction. Using abs() neither the order of the pins
            # nor the direction of rotation matters
            # If there is a Counter instead of Encoder, value() will aways be positive anyhow.
            # Divide by 2 because encoder operates with phases=2

            # At 200 nominal pulses/rev, counter.value()
            # will read 400 nominal pulses. For a sleep time of
            # 100 msec and 1.2 rev/sec normal speed, this means
            # 400*100/1000*1.2 = 40*1.2 = 48 pulses for each reading.
            # 48 pulses means a maximal error of 1 pulse in 48, about 2%
            # at nominal speed.
            # Reading at 100 millisec is similar to human reaction time,
            # so delay should quite tolerable.
            pulses =  abs(counter.value(0))/self.encoder_factor
            new_time = ticks_ms()
            time_ms = ticks_diff( new_time, last_time )

            # time_ms should never be 0, because there is a sleep_ms in this loop
            rpsec = (pulses/PULSES_PER_REV)/(time_ms/1000)
            # Apply low pass filter
            self.rpsec = lpf.filter( rpsec )
            #print(f">>> {rpsec=} {self.rpsec=}")
            last_time = new_time
            self._accumulate_readings( new_time, self.rpsec )

    def get_rpsec( self ):
        return self.rpsec

    def is_installed(self):
        return bool(self.counter_task)

    def _accumulate_readings( self, ticks, rpsec ):
        # This is for debugging only.
        # These lists are used in the diag.html page
        # to show a graph of the rpsec values over time.
        self.report_rps.append( rpsec ) 
        self.report_times.append( ticks )
        self.report_rps = self.report_rps[-20:]
        self.report_times = self.report_times[-20:]

    def irq_report( self ):
        # Used by diag.html to show a graph of the rpsec values over time.
        if not self.is_installed():
            return {}
        times = [] # used as X axis in graph
        if len(self.report_times)>0:
            t0 = self.report_times[0] # 0.0 to 1.0
            times = [ round(ticks_diff(x,t0)/1000,1) for x in self.report_times ]
        return {
            "dtList": [],
            "rpsecList": self.report_rps,
            "timesList": times,
            "now": ticks_ms(),
            "is_installed": self.is_installed(),
            "lower_threshold_rpsec": LOWER_THRESHOLD_RPSEC,
            "higher_threshold_rpsec": HIGHER_THRESHOLD_RPSEC,
            "normal_rpsec": NORMAL_RPSEC
        }

# This is the high level processing for the crank rotation sensor
# It uses TachoDriver.get_rps() to read the rotations per second,
# filters out small variations to clean up response.
# Main output is velocity for the MIDI player (get_normalized_rps), combining
# crank RPS and velocity set via browser (play.html)
# Main outputs:
#   Crank.is_turning() 
#   await Crank.wait_stop_turning()
#   Crank.get_normalized_rps()
#   Triggers asyncio.Event() according to registered events.
#   Events can be registered at the crank start, or some
#   time after crank starts to turn.
#   Adds info to get_progress() for tunelist.html and play.html.
class Crank:
    # Trigger events based on the crank revolution speed
    # like start and stop turning
    def __init__(self,tachometer_pin1, tachometer_pin2):
        self.logger = getLogger(__name__)

        # Set UI setting of velocity to 50, halfway from 0 to 100.
        self.set_velocity(50)
        # Initialize tachometer driver
        self.td = TachoDriver(tachometer_pin1, tachometer_pin2)
        
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
        # Faster access to get_rpsec
        get_rpsec = self.td.get_rpsec
        def rpsec_ge_higher_threshold():
            return get_rpsec()>=HIGHER_THRESHOLD_RPSEC
        
        # This code connects the tachometer sensor with the event that
        # starts a new tune in setlist

        # The while True: loop has the following phases:
        # 1. Wait for RPS to get higher than HIGHER_THRESHOLD_RPSEC
        #    (meaning the crank started turning).
        # 2. Wait a bit more for crank to stabilize
        # 3. Stay in this state while RPS higher than LOWER_THRESHOLD_RPSEC.
        #    (meaning: crank is turning at adequate speed)
        #    After some specified time in this state, asyncio.Events
        #    are triggered for example: to start music playback
        # 4. When exiting state 3, it means: crank stopped turning.
        #    Go back to 1. 
        
        while True:
            self.crank_is_turning = False
            # Wait for crank to start turning
            while not rpsec_ge_higher_threshold():
                await asyncio.sleep_ms(50)

            # Crank is now officialy turning
            self.logger.debug(f"---------> Crank now turning {get_rpsec()=}")    
            # setlist will only start tune after some time, so
            # if this was a fluke, setlist will wait it out.

            self.crank_is_turning = True

            # setlist.py schedules events to happen
            # when cranking starts and then after
            # some time, make these events happen
            events =list(self.events.items())
            events.sort( key=lambda x:x[0])
            while events:
                if rpsec_ge_higher_threshold():
                    break
                when_ms,ev = events.pop(0)
                await asyncio.sleep_ms(when_ms)
                ev.set() 

            # Wait until crank stops turning
            while rpsec_ge_higher_threshold():
                await asyncio.sleep_ms(50)

            # Record that crank is not turning
            self.crank_is_turning = False
            self.logger.debug(f"---------> Crank now stopped {get_rpsec()=}")
            
    def is_turning(self):
        return self.crank_is_turning 

    async def wait_stop_turning(self):
        if self.is_installed():
            while self.is_turning():
                await asyncio.sleep_ms(100)
        # If not installed, no waiting occurs, exit right away.
    
    def is_installed(self):
        return self.td.is_installed()

    def get_normalized_rpsec(self, tempo_follows_crank ):
        # Used in player.py to delay/hasten music
        # depending on crank speed AND UI velocity setting
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

# Rotary encoder to set tempo
# This is a potentiometer type rotary encoder,
# not the crank revolution sensor.
# The effect of this sensor is added to the crank sensor
class TempoEncoder:
    def __init__( self, crank, tempo_a, tempo_b, tempo_switch, rotary_tempo_mult ):
        self.logger = getLogger("TempoEncoder")
        self.crank = crank
        if not tempo_a or not tempo_b:
            # Both A and B input must be present for the
            # rotary encoder to work.
            return
        encoder = Encoder( 1, filter_ns=13000, # Highest value possible
                            phase_a=Pin( tempo_a, Pin.IN, Pin.PULL_UP ), 
                            phase_b=Pin( tempo_b, Pin.IN, Pin.PULL_UP ), 
                            phases=1)
        self.tempo_task = asyncio.create_task( self._tempo_process( encoder, rotary_tempo_mult ) )

        # Switch is optional
        if tempo_switch:
            switch = Pin( tempo_switch, Pin.IN, Pin.PULL_UP )
            self.switch_task = asyncio.create_task( self._switch_process( switch ))
        self.logger.info("init done")

    async def _tempo_process(self, encoder, rotary_tempo_mult ):
        encoder.value(0)
        while True:
            # Read velocity several times a second 
            await asyncio.sleep_ms(200)
            # Read pulses since last read, reset counter to 0.
            if (v := encoder.value(0)):
                self.crank.set_velocity_relative( v * rotary_tempo_mult )  
        
    async def _switch_process( self, switch ):
        # This detects a long press of the rotary encoder's switch
        # considering that the switch is very, very noisy and bouncy.
        while True:
            await asyncio.sleep_ms(300)
            # Wait until switch pressed (.value()==0 is "pressed")
            if switch.value() == 0:
                # Switch is now "on", see if it stays 
                # steadily on
                # for about 0.8 seconds. 
                # I have a rather
                # low quality rotary encoder where the
                # switch toggles when the rotary encoder counts.
                # Or perhaps I don't know how to use that thing.
                v = 0
                for _ in range(40):
                    # Sample frequently
                    await asyncio.sleep_ms(20)
                    if(v := switch.value()): 
                        break
                # Was switch never off during this time?
                if v == 0:
                    self.crank.set_velocity(50)

#>>>Test counter, will plug TachoDriver and generate random RPS
# from random import random
# class DebugCounter:
#     def __init__(self):
#         self.time_ant = ticks_ms()
#         self.repetitions = 0

#     def value( self, newvalue=None ):
#         self.repetitions -= 1
#         if self.repetitions < 0:
#             # 200 stripes = 400 pulses/sec at 1 RPS
#             # 800 pulses*100ms = 80 pulses
#             # should result in 2.4 RPS
#             self.current_val = random()*60
#             self.repetitions = random()*30

#         #newt = ticks_ms()
#         #dt = ticks_diff(newt, self.time_ant)
#         #self.time_ant = newt
#         return self.current_val

# async def debug():
#     print("TachoDriver Debug started")
#     from drehorgel import crank
#     crank.td.counter_task.cancel()
#     newcounter = DebugCounter()
#     crank.td.counter_task = asyncio.create_task( crank.td._sensor_process( newcounter ))

# asyncio.create_task( debug() )