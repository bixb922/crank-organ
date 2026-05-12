
# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

import asyncio
from time import ticks_ms, ticks_diff

from machine import Pin
# Counter/Encoder requires MicroPython 1.27 or later
from machine import Encoder, Counter # type:ignore

from minilog import getLogger
from drehorgel import config
from scheduler import is_player_active

# Factor to convert the milliseconds  to revolutions per second (rpsec)
# and vice-versa. rpsec = _FACTOR/msec, msec = _FACTOR/rpsec
_FACTOR = 1000/config.pulses_per_revolution
    
def rpsec_filter(filter_window_len, stopped_rpsec, higher_threshold_rpsec):
    if filter_window_len == 0:
        # yield raw always,
        while True:
            raw = yield 0 # Return number to keep pylint happy
            yield raw

    moving = [0]
    while True:
        raw = yield 0 # Return number to keep pylint happy
        moving.append( raw )
        while len(moving)>filter_window_len:
            moving.pop(0)

        big_up = min(moving)<stopped_rpsec and raw>higher_threshold_rpsec
        big_down = max(moving)>higher_threshold_rpsec and raw<stopped_rpsec
        
        if big_up or big_down:
            # Make a faster response if crank starts or stops.
            # Reduce moving window to the minimum to get fast response
            moving = [raw]
            yield raw
        else:
            yield sum(moving)/len(moving)

# This is the low level driver for the crank rotation sensor
# Main output is get_rps() which returns the "rotations per second"
# of the crank.
class TachoDriver:
    def __init__(self, tachometer_pin1, tachometer_pin2):
        self.logger = getLogger(__name__)
        self.counter_task = None
        self.counter = None
        self.rpsec = 0
        # For diag.html report of crank frequencies
        self.report_rps = []

        if not tachometer_pin1 or config.automatic_delay:
            # Disable if first pin was not defined.
            # Disable crank sensor for "automatic_delay" so music
            # will not pause at the end of the song.
            self.logger.debug("Configuration does not enable crank sensor")
            return
        
        # Maximum value for filter_ns is 12787.5 nanosec = 13 microseconds
        # if filter_ns is higher, the highest possible value is set.
        try:
            if tachometer_pin1 and not tachometer_pin2:
                # One pin defined means: simple counter for crank
                # Count 2 per sensor pulse (highest rate possible)
                self.counter = Counter( 0, 
                        Pin( tachometer_pin1, Pin.IN, Pin.PULL_UP ), 
                        direction=Counter.UP,
                        edge=Counter.RISING + Counter.FALLING, 
                        filter_ns=20_000) # Highest filter value possible
            else:
                # Two pins defined means: rotary encoder for crank
                # Count 4 per sensor pulse (highest rate possible)
                self.counter = Encoder( 0,
                        phase_a=Pin( tachometer_pin1, Pin.IN, Pin.PULL_UP ), 
                        phase_b=Pin( tachometer_pin2, Pin.IN, Pin.PULL_UP ), 
                        phases=4, 
                        filter_ns=20_000) # Highest filter value possible
            # Start the sensor process
            self.counter_task = asyncio.create_task( self._sensor_process() )
        except Exception as e:
            self.logger.exc( e, "Could not initialize counter/encoder")


        

    async def _sensor_process( self ):
        if not self.counter:
            return
        last_time = ticks_ms()
        self.counter.value(0) # Reset value counter to 0
        # step: Delay between 2 reads of the crank in millisec
        # If too small, precision decreases
        # If too large, response to changes is slower
        step = config.crank_interval

        filter = rpsec_filter( config.filter_window_len, 
                            config.stopped_rpsec,
                            config.higher_threshold_rpsec)
        if config.filter_window_len:
            self.logger.info(f"Crank filter enabled with filter_window_len={config.filter_window_len}, stopped_rpsec={config.stopped_rpsec}, lower_threshold_rpsec={config.lower_threshold_rpsec}, higher_threshold_rpsec={config.higher_threshold_rpsec}")
        else:
            self.logger.info(f"Crank filter disabled")

        while True:
            # Wait approximately "step" milliseconds
            # sleep_ms does not need to be precise.

            # The goal is to have about 50 pulses per step.
            # 50 pulses means a maximal error of 1 pulse in 50, about 2%
            # at nominal speed.
            await asyncio.sleep_ms(step)

            # Get pulses since last call, i.e. value(0) resets
            # the counter to 0. 
            # Take abs() because if a Encoder is present, value
            # can be negative if crank is turned in the opposite
            # direction. When using abs() neither the order of the pins
            # nor the direction of rotation matters

            # Don't divide pulses by number of phases to make this reading here equal
            # to what test crank button on web page reports.
            pulses =  abs(self.counter.value(0))
            new_time = ticks_ms()
            time_ms = ticks_diff( new_time, last_time )
            last_time = new_time

            # time_ms should never be 0, because there is a sleep_ms in this loop
            # so there should never a division by 0 here
            raw = pulses * _FACTOR / time_ms

            # Apply filter
            next(filter) # Needed to advance the generator
            self.rpsec = filter.send( raw )

            self._accumulate_readings( new_time, raw, self.rpsec )

    def get_rpsec( self ):
        return self.rpsec

    def is_installed(self):
        # If counter task not started or cancelled, there is no crank.
        return bool(self.counter_task)

    def _accumulate_readings( self, ticks_start, raw, rpsec):
        # This is for debugging only.
        # These lists are used in the diag.html page
        # to show a graph of the rpsec values over time.
        self.report_rps.append( ( ticks_start, raw, rpsec) )
        
        # Keep 3000 milliseconds (3 seconds) of data
        while ticks_diff( self.report_rps[-1][0], self.report_rps[0][0])>3000:
            self.report_rps.pop(0) 

        # Dump raw and filtered data to file for debugging. 
        self._dump_tacho( raw, self.rpsec ) 


    def irq_report( self ):
        # Used by diag.html to show a graph of the rpsec values over time.
        if not self.is_installed():
            return {}
        times = [] # used as X axis in graph
        if len(self.report_rps)>0:
            t0 = self.report_rps[0][0] # 0.0 to 1.0
            times = [ round(ticks_diff(x,t0)/1000,1) for x,_,_ in self.report_rps ]
        return {
            "dtList": [],
            "rpsecList": [x for _,_,x in self.report_rps],
            "rawList": [x for _,x,_ in self.report_rps],
            "timesList": times,
            "now": ticks_ms(),
            "is_installed": self.is_installed(),
            "stopped_rpsec": config.stopped_rpsec,
            "lower_threshold_rpsec": config.lower_threshold_rpsec,
            "higher_threshold_rpsec": config.higher_threshold_rpsec ,
            "normal_rpsec": config.normal_rpsec
        }
    
    def raw_value( self ):
        # Used in pinout.html to test crank encoder/counter
        if not self.counter:
            return ""
        if not hasattr(self, "last_value"):
            self.last_value = 0
            self.count = 0
            self.counter_task.cancel() #type:ignore
            self.counter.value(0)
        val = self.counter.value()
        if val == self.last_value:
            self.count += 1
            # reset if no change during about 2 sec
            if self.count >= 6: 
                self.counter.value(0)
                val = 0
        else:
            self.count = 0
            self.last_value = val
        return val


    def _dump_tacho( self, raw, filtered ):
        # For debugging of raw and filtered crank data.
        if not config.dump_tacho_data:
            return
        if not hasattr( self, "tacho_data"):
            self.tacho_data = []
            self.t0 = ticks_ms()
            return

        dt = ticks_diff(ticks_ms(), self.t0)
        self.t0 = ticks_ms()
        self.tacho_data.append( (dt,raw,filtered) )
        # keep accumulating raw data if player is active.
        # If player is not active and data is long, store
        # If player is not active and no significant data,
        # then keep about 2 seconds of tacho data to show the
        # start.
        if not is_player_active():
            leadin_samples = 2000//config.crank_interval
            if len(self.tacho_data) <= leadin_samples+3:
                while len(self.tacho_data)>leadin_samples:
                    self.tacho_data.pop(0)
            else:
                # Player not active and tacho_data has accumulated readings.
                from drehorgel import timezone
                from fileops import write_json
                fn = "tacho_" + timezone.now_ymdhms().replace(" ","_") + ".json"
                self.logger.debug(f"Dumping tacho data len={len(self.tacho_data)} to {fn}")
                # >>> limit flash space!!
                write_json( self.tacho_data, fn )
                self.tacho_data = []

# This is the high level processing for the crank rotation sensor
# It uses TachoDriver.get_rps() to read the rotations per second,
# filters out small variations to clean up response.
# Main output is velocity for the MIDI player (get_normalized_rps), combining
# crank RPS and velocity set via browser (play.html)
# Main interfaces:
#   crank.is_turning() 
#   await crank.wait_start_turning()
#   await crank.wait_stop_turning()
#   crank.get_normalized_rps()
#   Triggers registered event.
#   Adds crank info to get_progress() for tunelist.html and play.html.
class Crank:
    # Trigger events based on the crank revolution speed
    # like start and stop turning
    def __init__(self,tachometer_pin1, tachometer_pin2):
        self.logger = getLogger(__name__)

        # Set UI setting of velocity to 50, halfway from 0 to 100.
        self.set_velocity(50)
        # Initialize tachometer driver
        self.td = TachoDriver(tachometer_pin1, tachometer_pin2)

        # At startup crank is stopped
        # Also: when not installed, crank never starts
        # and is always stopped.
        self.crank_stopped = asyncio.Event()
        self.crank_stopped.set()
        self.crank_turning = asyncio.Event()
        # Will be replaced by register_start_crank_event:
        self.registered_event = asyncio.Event()

        # A task to monitor the crank and set/reset the events
        if self.is_installed():
            self.crank_monitor_task = asyncio.create_task( self._start_stop_monitor() )
        self.logger.debug("crank init ok")
    
    def register_start_crank_event( self, ev ):
        # Injected by setlist.
        self.registered_event = ev

    async def _start_stop_monitor( self ):
         # This task sets/resets events when crank movement
         # starts and stops.
         while True:
            await asyncio.sleep_ms(100)
            r = self.td.get_rpsec()
            if r <= config.lower_threshold_rpsec and not self.crank_stopped.is_set():
                self.crank_stopped.set()
                self.crank_turning.clear()
            elif r >= config.higher_threshold_rpsec:
                # Handle registered event
                if config.wait_stop_turning:
                      # set only on transition from stopped to turning
                      # Allows code to clear event and detect transition from
                      # turning to stopped.
                      if not self.crank_turning.is_set():
                        self.registered_event.set()
                else:
                    # keep set always while crank is turning
                    self.registered_event.set()

                if not self.crank_turning.is_set(): # optimize CPU
                    self.crank_stopped.clear()
                    self.crank_turning.set()

    def is_turning(self):
        return self.crank_turning.is_set()

    async def wait_stop_turning(self):
        await self.crank_stopped.wait() # type:ignore

    async def wait_start_turning(self):
        await self.crank_turning.wait() # type:ignore

    def is_installed(self):
        return self.td.is_installed()

    def get_normalized_rpsec(self, tempo_follows_crank ):
        # Used in player.py to delay/hasten music
        # depending on crank speed AND UI velocity setting
        # If no crank, UI can still change tempo!
        if tempo_follows_crank:
            return self.td.get_rpsec() / config.normal_rpsec * self.tempo_multiplier 
        return self.tempo_multiplier 

    def set_velocity_relative( self, change):
        # Change velocity settings relative to current setting
        ui_vel = min(max(self.ui_velocity+change,0),100)
        self.set_velocity( ui_vel )

    def set_velocity(self,ui_vel):
        # Velocity is a superimposed manual control via UI to alter the "normal"
        # playback speed. elf.ui_velocity is the velocity as set by the ui
        # (50=normal, 0=lowest, 100=highest).
        # TempoEncoder can also set this velocity. Both are coordinated.

        self.ui_velocity = ui_vel
        # The UI sets self.ui_velocity to a value from 0 and 100, normal=50.
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
# The effect of this sensor is added to the crank sensor and UI setting
# Keep if needed in the future
# class TempoEncoder:
#     def __init__( self, crank, tempo_a, tempo_b, tempo_switch, rotary_tempo_mult ):
#         self.logger = getLogger("TempoEncoder")
#         self.crank = crank
#         if not tempo_a or not tempo_b:
#             # Both A and B input must be present for the
#             # rotary encoder to work.
#             return
#         encoder = Encoder( 1, filter_ns=13000, # Highest value possible
#                             phase_a=Pin( tempo_a, Pin.IN, Pin.PULL_UP ), 
#                             phase_b=Pin( tempo_b, Pin.IN, Pin.PULL_UP ), 
#                             phases=1)
#         self.tempo_task = asyncio.create_task( self._tempo_process( encoder, rotary_tempo_mult ) )

#         # Switch is optional
#         if tempo_switch:
#             switch = Pin( tempo_switch, Pin.IN, Pin.PULL_UP )
#             self.switch_task = asyncio.create_task( self._switch_process( switch ))
#         self.logger.debug("init ok")

#     async def _tempo_process(self, encoder, rotary_tempo_mult ):
#         encoder.value(0)
#         while True:
#             # Read velocity several times a second 
#             await asyncio.sleep_ms(200)
#             # Read pulses since last read, reset counter to 0.
#             if (v := encoder.value(0)):
#                 self.crank.set_velocity_relative( v * rotary_tempo_mult )  
        
#     async def _switch_process( self, switch ):
#         # This detects a long press of the rotary encoder's switch
#         # considering that the switch is very, very noisy and bouncy.
#         while True:
#             await asyncio.sleep_ms(300)
#             # Wait until switch pressed (.value()==0 is "pressed")
#             if switch.value() == 0:
#                 # Switch is now "on", see if it stays 
#                 # steadily on
#                 # for about 0.8 seconds. 
#                 # I have a rather
#                 # low quality rotary encoder where the
#                 # switch toggles when the rotary encoder counts.
#                 # Or perhaps I don't know how to use that thing.
#                 v = 0
#                 for _ in range(40):
#                     # Sample frequently
#                     await asyncio.sleep_ms(20)
#                     if(v := switch.value()): 
#                         break
#                 # Was switch never off during this time?
#                 if v == 0:
#                     self.crank.set_velocity(50)

# This code will plug TachoDriver and generate random RPS

class DebugCounter:
    def __init__(self):
        self.value_list = []
        # Normal rpsec in pulses per config.crank_interval
        self.normal = config.pulses_per_revolution*config.normal_rpsec/(1000/config.crank_interval)
        self.last_value = 0
        self.t0 = ticks_ms()

    def value( self, newvalue=None ):
        from random import random
        dt = ticks_diff(ticks_ms(), self.t0)
        self.t0 = ticks_ms()
        # calculate pulses equivalent to config.normal_rpsec for the time since last call to value()
        normal = self.normal * dt/config.crank_interval

        if not self.value_list:
            # Value list is empty, refill
            if random() < 0.1:
                self.value_list = [ self.last_value*1.5, self.last_value*0.7, self.last_value*0.8 ]
            elif random() < 0.1:
                self.value_list = [normal/10]
            elif random() < 0.1:
                self.value_list = [normal*1.4]
            elif random() < 0.1:
                x = self.last_value
                self.value_list = [ x*1.1, x*0.9, x*0.7, x*0.6, x*0.5, x*0.4, x*0.3, x*0.2]
            elif random() < 0.1:
                x = self.last_value
                self.value_list = [ x*0.4, x*0.5, x*0.7, x*0.9, x*0.9, x*1.1, x*1.2, x*1.3]
            elif random() < 0.1:
                self.value_list = [0]*10
            else:
                repetitions = round(random()*20)+1
                self.value_list = [normal*( 1+random()*0.05-0.025 ) for _ in range(repetitions)]

        self.last_value = self.value_list.pop(0)
        return self.last_value
    
    async def start_debug( self ):
        while True:
            await asyncio.sleep_ms(200)
            try:
                from drehorgel import crank
                break
            except:
                pass
        if crank.td.counter:
            # Monkey patch function to read counter value. Rest of
            # TachoDriver continues to be enabled.
            crank.td.counter.value = self.value
            crank.logger.info("Inject tacho debug data enabled")

if config.debug_tacho:
    debug_task = asyncio.create_task( DebugCounter().start_debug() )

