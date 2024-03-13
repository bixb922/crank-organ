# (c) 2023 Hermann Paul von Borries
# MIT License
# Crank rotation speed sensor. Still in testing phase.

import asyncio
import micropython
from time import ticks_ms, ticks_diff
from machine import Pin
from array import array


if __name__ == "__main__":
    import sys
    sys.path.append("software/mpy")
    
from minilog import getLogger
from pinout import gpio

# Number of pulses (1 pulse = off + on) per revolution
# If optical stripes = number of stripes*2
# since the IRQ is fired both for rising and falling edge
PULSES_PER_REV = const(32)
# Less than these minimum means "stopped" or "not turning"

# Factor to convert the milliseconds stored to revolutions per second (rpsec)
FACTOR = 1000/PULSES_PER_REV

LOWER_THRESHOLD_RPSEC = 0.5
HIGHER_THRESHOLD_RPSEC = 0.7
# "Normal" speed, when MIDI speed == real speed
NORMAL_RPSEC = const(1.2)
# Maximum expected RPM. This limit should be never achieved in practice.
# Interrupts will be lost if exceeded, this value is used for debouncing.
MAX_EXPECTED_RPSEC = const(3)
# Time for signal to settle on transitions (for debouncing)
# This is actually a time during which the interrupts are disregarded.
# and is counted from the first interrupt of a bouncing sequence.
MINIMUM_MSEC_BETWEEN_IRQ = int(1000/MAX_EXPECTED_RPSEC/PULSES_PER_REV)
# Maximum time between IRQ, more than this means "stopped"

# Size of buffer of stored periods
IRQ_BUFFER_SIZE = 4

# for debugging>>>>>
debug_buffer = array("i",(0 for _ in range(1000)))
debug_buffer_pointer = 0

class TachoDriver:
    # The TachoDriver gets interrupts from the pin connected
    # to the crank sensor and computes revolutions per sec
    # to be read with TachoDriver.get_rpsec()
    # If no tachometer_pin, TachoDriver returns NORMAL_RPSEC
    def __init__(self,tachometer_pin):
        self.tachometer_pin = tachometer_pin
            
        self.rpsec = NORMAL_RPSEC
        # Start with a high value
        self.avgdt = 10_000
        self.last_irq_time = ticks_ms()
        self.dt = 10_000 # >>>>>DEBUG >>>>>>>>>>>>>>>
        self.irq_pointer = 0
        self.irq_buffer = array("i", (0 for _ in range(IRQ_BUFFER_SIZE)))

        if not self.tachometer_pin:
            return
        
        if tachometer_pin!=999:
            micropython.alloc_emergency_exception_buf(100)
            tachometer_device = Pin(tachometer_pin,Pin.IN)
            tachometer_device.irq( trigger=Pin.IRQ_RISING+Pin.IRQ_FALLING,handler=self.pin_irq)
        else:
            return 
        
    def pin_irq(self,pin):
        global debug_buffer, debug_buffer_pointer
        # Process interrupt request (IRQ) from tachometer pin
        t = ticks_ms()
        dt = ticks_diff(t,self.last_irq_time)
        # Discard very frequent interrupts for debouncing.
        if dt>MINIMUM_MSEC_BETWEEN_IRQ:
            # Store the time this interrupt occurred 
            # and the time since the the previous interrupt
            self.last_irq_time = t
            self.dt = dt #>>>>> store dt for DEBUG only
            p = self.irq_pointer
            self.irq_buffer[p] = dt
            self.irq_pointer = (p+1)%IRQ_BUFFER_SIZE
        # DEBUG>>>>
        debug_buffer[debug_buffer_pointer] = dt
        debug_buffer_pointer = (debug_buffer_pointer+1)%len(debug_buffer)

        
    def get_rpsec(self):
        dt_since_last_irq = ticks_diff(ticks_ms(),self.last_irq_time)
        # >>>> debug, avgdt can be local variable
        self.avgdt = sum(self.irq_buffer)/IRQ_BUFFER_SIZE
        if self.avgdt>dt_since_last_irq:
            return FACTOR/self.avgdt
        # No interrupts have arrived (tacho slowing down)
        # Use time since last interrupt to calculate revolutions per second
        # as best prediction of what is happening...
        return FACTOR/dt_since_last_irq
    
    def is_installed(self):
        return bool(self.tachometer_pin)


class Crank:
    def __init__(self,tachometer_pin):
        self.logger = getLogger(__name__)

        # Set UI reference to 50, halfway from 0 to 100.
        self.set_velocity(50)
        # Initialize tachometer driver
        self.td = TachoDriver(tachometer_pin)
        
        # More events will be registered later
        self.events={}
        # First event: start crank turning
        self.start_turning_event = self.register_event(0)
        
        self.stop_turning_event = asyncio.Event()
        self.stop_turning_event.set()
        
        # A task to monitor the crank
        self.crank_monitor_task = asyncio.create_task(self._crank_monitor_process())
        self.logger.debug("init ok")
        
    def register_event(self,when_ms):
        # Can register one event for each time only.
        if not when_ms in self.events:
        # Register an event to be set "when_ms" milliseconds after
        # the crank starts to turn.
            self.events[when_ms] = asyncio.Event()
        return self.events[when_ms]

    async def wait_stop_turning_event(self):
        await self.stop_turning_event.wait()
    
    async def _crank_monitor_process(self):
        # This connects the tachometer sensor with the event that
        # starts a new tune in setlist
        last_rpsec = 0
        # Turning hasn't started
        time_when_turning_started = None
        some_pulses = int(4*HIGHER_THRESHOLD_RPSEC/PULSES_PER_REV)
        while True:
            # Wait for crank to start turning
            while self.td.get_rpsec()<HIGHER_THRESHOLD_RPSEC:
                await asyncio.sleep_ms(50)
                
            # Guard against spurious events, wait for some pulses
            await asyncio.sleep_ms(some_pulses)
            
            time_when_turning_started = ticks_ms()
            # Check until all registered events have been triggered and some
            max_time_to_monitor = max(w for w in self.events.keys())+1000
            while self.td.get_rpsec()>LOWER_THRESHOLD_RPSEC:
                await asyncio.sleep_ms(100)
                time_since_start = ticks_diff(ticks_ms(),time_when_turning_started)
                for when_ms,ev in self.events.items():
                    if time_since_start>=when_ms and not ev.is_set():
                        ev.set()
                        self.stop_turning_event.clear()
                        
                if time_since_start>max_time_to_monitor:
                    # Save some CPU, don't continue to monitor crank turning
                    # until turning stops. All events have been generated
                    break
                    
            # Wait until crank stops turning
            while self.td.get_rpsec()>LOWER_THRESHOLD_RPSEC:
                await asyncio.sleep_ms(100)
                
            # Crank stopped turning, set/clear events.
            self.stop_turning_event.set()
            for ev in self.events.values():
                ev.clear()

    def is_turning(self):
        return self.start_turning_event.is_set()

    def is_installed(self):
        return self.td.is_installed()

    def get_normalized_rpsec(self):
        # Used in player.py to delay/hasten music
        # depending on crank speed
        return self.td.get_rpsec() * self.velocity_multiplier
        
    def set_velocity(self,ui_vel):
        # Velocity is a superimposed manual control via UI to alter the "normal"
        # playback speed. Crank._ui_velocity is the velocity as set by the ui
        # (50=normal, 0=lowest, 100=highest).

        self.ui_velocity = ui_vel
        # The UI sets _ui_velocity to a value from 0 and 100, normal=50.
        # _ui_velocity is a multiplier, 1=normal, 2=double speed, 0.5=half speed
        # f(0) => 0.5
        # f(50) => 1
        # f(100) => 2
        # Calculate the multiplier needed by get_normalized_rpsec
        self.velocity_multiplier = (
            ui_vel * ui_vel / 10000 + ui_vel / 200 + 0.5
        ) / NORMAL_RPSEC


    def complement_progress(self,progress):
        progress["velocity"] = self.ui_velocity
        progress["rpsec"] = self.td.get_rpsec()
        progress["is_turning"] = self.is_turning()
        progress["normalized_rpsec"] = self.get_normalized_rpsec()
        
crank = Crank(gpio.tachometer_pin)

if __name__ == "__main__":
    from random import random
    import neopixel
    # Test
    # Replace tachometer with simulated one
    crank = Crank(5)
    td = crank.td
    
    async def getrawdata():
        #genirq_task = asyncio.create_task(genirq(td))
        print("main started")
        while debug_buffer_pointer < len(debug_buffer)-2:
            await asyncio.sleep_ms(500)
            p = debug_buffer_pointer/len(debug_buffer)*100
            print(f"{debug_buffer_pointer} interrupts so far {p:5.1f}%")
        #with open("tachosample.tsv", "w") as file:
        #    file.write("\n")
        #    for k in debug_buffer:
        #        file.write(f"\t{k}\n")
        #    print("tachosample.tsv written")

        
    async def testcrank():
        #genirq_task = asyncio.create_task(genirq(td))
        start_ev = crank.register_event( 0 )
        stable_ev = crank.register_event( 500 )
        bored_ev = crank.register_event( 3000 )
        while True:
            cit = "       "
            if crank.is_turning():
                cit = "turning"
            start = "Y" if start_ev.is_set() else " "
            stable = "Y" if stable_ev.is_set() else " "
            bored = "Y" if bored_ev.is_set() else " "
            rpsec = crank.td.get_rpsec()
            overlt = "Y" if rpsec > LOWER_THRESHOLD_RPSEC else " "
            overht = "Y" if rpsec > HIGHER_THRESHOLD_RPSEC else " "
            stopped = "Y" if crank.stop_turning_event.is_set() else " "
            tdlast = ticks_diff(ticks_ms(),td.last_irq_time)
            print(f"rpsec={td.get_rpsec():2.1f} {cit} {start=} {stable=} {bored=} {stopped=} {overlt=} {overht=} {td.dt=:4d} {td.avgdt=:4.0f}")
            await asyncio.sleep_ms(100)

            
    async def genirq(td):
        dt = 1000
        changed = ticks_ms()
        last_t = changed
        while True:
            t = ticks_ms()
            if ticks_diff(t,changed)>1000:
                dt = round((random()*80)+25)
                if random()>0.9:
                    dt = 1000
                print("new interval", dt)
                changed = t
            last_t = t
            await asyncio.sleep_ms(int(dt*(1+random()/5.0)))
            td.pin_irq(0)

    asyncio.run(testcrank())