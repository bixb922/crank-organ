# (c) 2023 Hermann Paul von Borries
# MIT License
# Touchpad asyncio driver, detects button down event in background
# and triggers events defined by registering.
import machine
import asyncio
import time

from config import config
from led import led

# Polling interval
MSEC_BETWEEN_SAMPLES = const(100)
# Time for TouchPad signal to settle == time to ignore bouncing,
# TouchPad will not sense a second click if time less than MSEC_SETTLE
MSEC_SETTLE = const(100)
# If two touches within this interval, it's a "double touch"
DOUBLE_TOUCH_TIME = const(1000)


class TouchButton:
    def __init__(self, gpio_pin):
        # The TouchButton allows to register a list
        # of asyncio.Events() por action (up, down, double down)
        # Hand goes up from touchpad:
        self.up_events = []
        # Hand goes down on touchpad:
        self.down_events = []
        # Two down events in succesion (like a "double click"):
        self.double_events = []
        # Sensitivity of touchpad: size of change to cause an event
        self.big_change = int(config.get_int("touchpad_big_change", 10000))
        
        if gpio_pin:
            self.gpio_pin = gpio_pin
            self.tp = machine.TouchPad(machine.Pin(gpio_pin))
            self.task = asyncio.create_task(self.tp_process())
        # If no gpio_pin, don't assign button, don't create task.
        # Events will never get set.

    def register_up_event(self, ev):
        # Event when lifting hand up leaving touch pad
        if ev not in self.up_events:
            self.up_events.append(ev)
    
    def register_down_event(self,ev):
        # Not used by now.
        # Event when putting hand down on touch pad
        if ev not in self.down_events:
            self.down_events.append(ev)
    
    def register_double_event(self,ev):
        # Event when twice down in a row (similar to double-click on PC but slower)
        if ev not in self.double_events:
            self.double_events.append(ev) 

    def set_events(self, event_list):
        for ev in event_list:
            ev.set()

    async def tp_process(self):
        # At startup, wait a bit before reacting and for touchpad reading to settle
        await asyncio.sleep(1)
        # Last_up and previous_up are times of previous touches
        # Initialize last_up and previous up in the very past
        previous_up = time.ticks_add(time.ticks_ms(),-DOUBLE_TOUCH_TIME)
        last_up = previous_up
        tpval_ant = self.tp.read()
        while True:
            await asyncio.sleep_ms(MSEC_BETWEEN_SAMPLES)
            tpval = self.tp.read()
            # See if this is a transition: hand leaving the touchpad
            if tpval-tpval_ant<-self.big_change:
                led.touch_flash()
                # Touch end: set event to publish this
                self.set_events( self.up_events )
                # Keep time of last 2 touch events
                previous_up = last_up
                last_up = time.ticks_ms()
                # See if this is a "double touch"
                if time.ticks_diff(last_up,previous_up)<DOUBLE_TOUCH_TIME:
                    self.set_events( self.double_events )
                    # 3 touch down in a row will yield 2 double events...
                # Wait for touchpad value to settle, and read again
                await asyncio.sleep_ms(MSEC_SETTLE)
            # See if this is a transition: hand touching the touchpad
            elif tpval-tpval_ant>self.big_change:
                # Touch down: show led, activate event, wait for signal to settle
                led.touch_start()
                self.set_events( self.down_events )
                await asyncio.sleep_ms(MSEC_SETTLE)
                
            tpval_ant = tpval

