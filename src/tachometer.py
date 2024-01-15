# (c) 2023 Hermann Paul von Borries
# MIT License
# Crank rotation speed sensor. Still in testing phase.
# >>> REFACTOR
import asyncio
import micropython
from array import array
from time import ticks_ms, ticks_diff,ticks_add
from machine import Pin


if __name__ == "__main__":
    import sys
    sys.path.append("software/mpy")
    
from minilog import getLogger
from pinout import gpio

# Number of pulses (1 pulse = off + on) per revolution
# If optical stripes = number of stripes*2
# If hall sensor magnets = number of magnets
PULSES_PER_REV = const(20)
# Less than these minimum means "stopped" or "not turning"
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


# Factor to convert the milliseconds stored to revolutions per second (rpsec)
FACTOR = 1000/PULSES_PER_REV

class TachoDriver:
    # The TachoDriver gets interrupts from the pin connected
    # to the crank sensor and computes revolutions per sec
    # to be read with TachoDriver.get_rpsec()
    # If no tachometer_pin, TachoDriver returns NORMAL_RPSEC
    def __init__(self,tachometer_pin):
        self.tachometer_pin = tachometer_pin
            
        self.rpsec = NORMAL_RPSEC
        # Start with a high value
        self.dt = 10_000
        self.last_irq_time = ticks_ms()

        if not self.tachometer_pin:
            return
        
        if tachometer_pin!=999:
            micropython.alloc_emergency_exception_buf(100)
            tachometer_device = Pin(tachometer_pin,Pin.IN)
            tachometer_device.irq( trigger=Pin.IRQ_RISING+Pin.IRQ_FALLING,handler=self.pin_irq)
        else:
            return # >>>>> DEBUG USING CALL TO pin_irq
            # Debugging using timer interrupts, no real sensor
            #from machine import Timer
            #self.tim0 = Timer(0)
            #self.tim0.init(period=110,mode=Timer.PERIODIC,callback=self.pin_irq)

    
    def pin_irq(self,pin):
        # Process interrupt request (IRQ) from tachometer pin
        t = ticks_ms()
        dt = ticks_diff(t,self.last_irq_time)
        # Discard very frequent interrupts for debouncing.
        if dt>MINIMUM_MSEC_BETWEEN_IRQ:
            # Store the time this interrupt occurred 
            # and the time since the the previous interrupt
            self.last_irq_time = t
            self.dt = dt
            

    def get_rpsec(self):
        dt_since_last_irq = ticks_diff(ticks_ms(),self.last_irq_time)
        if self.dt>dt_since_last_irq:
            return FACTOR/self.dt
        # No interrupts have arrived (tacho slowing down)
        # Use time since last interrupt to calculate revolutions per second
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
        # First event: start crank turning
        self.events = [(asyncio.Event(),0)]
        # self.events[0][0] is the "start crank turning" event
        
        self.stop_turning_event = asyncio.Event()
        self.stop_turning_event.set()
        
        # A task to monitor the crank
        self.crank_monitor_task = asyncio.create_task(self._crank_monitor_process())
        self.logger.debug("init ok")
        
    def register_event(self,when_ms):
        if when_ms==0:
            # The "when" == 0 event has already been registered in __init__
            return self.events[0][0]
        
        # Register an event to be set when_ms milliseconds after
        # the crank starts to turn.
        ev = asyncio.Event()
        self.events.append((ev,when_ms))
        return ev
    
    def register_stop_turning_event(self,ev):
        self.stop_turning_event = ev
        if not self.is_installed():
            self.stop_turning_event.set()
        
    async def _crank_monitor_process(self):
        # This connects the tachometer sensor with the event that
        # starts a new tune in setlist
        last_rpsec = 0
        # Turning hasn't started
        time_when_turning_started = None
        while True:
            # Wait for crank to start turning
            while self.td.get_rpsec()<HIGHER_THRESHOLD_RPSEC:
                await asyncio.sleep_ms(100)
                
            # Guard against spurious events
            await asyncio.sleep_ms(100)
            
            time_when_turning_started = ticks_ms()
            # Check until all registered events have been triggered and some
            max_time_to_monitor = max(w for (ev,w) in self.events)+1000
            while self.td.get_rpsec()>LOWER_THRESHOLD_RPSEC:
                await asyncio.sleep_ms(100)
                time_since_start = ticks_diff(ticks_ms(),time_when_turning_started)
                for (ev,when_ms) in self.events:
                    if time_since_start>=when_ms and not ev.is_set():
                        ev.set()
                        self.stop_turning_event.clear()
                        
                if time_since_start>max_time_to_monitor:
                    # Save some CPU, don't continue to monitor crank turning
                    # until turning stops.
                    break
                    
            # Wait until crank stops turning
            while self.td.get_rpsec()>LOWER_THRESHOLD_RPSEC:
                await asyncio.sleep_ms(100)

            self.stop_turning_event.set()
                
            for (ev,when_ms) in self.events:
                ev.clear()

    def is_turning(self):
        return self.events[0][0].is_set()

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
    from machine import Timer
    from random import random
    # Test
    # Replace tachometer with simulated one
    crank = Crank(999)
    td = crank.td
    async def main():
        print("main started")
        n = 0
        genirq_task = asyncio.create_task(genirq(td))
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
            print(f"rpsec={td.get_rpsec():2.1f} {cit} {start=} {stable=} {bored=} {stopped=} {overlt=} {overht=} {td.dt=:4d}")
            await asyncio.sleep_ms(100)

            
    async def genirq(td):
        dt = 1000
        changed = ticks_ms()
        last_t = changed
        while True:
            t = ticks_ms()
            if ticks_diff(t,changed)>1000:
                dt = round((random()*80)+30)
                if random()>0.9:
                    dt = 1000
                print(f"new interval", dt)
                changed = t
            last_t = t
            await asyncio.sleep_ms(dt)
            td.pin_irq(0)
            
            
    asyncio.run(main())