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
        # Only release event, no touch event
        # Events are defined by registering a asyncio.Event()
        ignore = asyncio.Event()
        self.up_event = ignore
        self.down_event = ignore
        self.double_event = ignore
        
        self.big_change = int(config.get_int("touchpad_big_change", 10000))
        
        if gpio_pin:
            self.gpio_pin = gpio_pin
            self.tp = machine.TouchPad(machine.Pin(gpio_pin))
            self.task = asyncio.create_task(self.tp_process())
        # If no gpio_pin, don't assign button, don't create task.
        # Event will never get set.

    def register_up_event(self, ev):
        # Event when lifting hand up leaving touch pad
        self.up_event = ev
    
    def register_down_event(self,ev):
        # Not used?
        # Event when putting hand down on touch pad
        self.down_event = ev
    
    def register_double_event(self,ev):
        # Event when twice down in a row (similar to double-click on PC but slower)
        self.double_event = ev
        
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
            if tpval - tpval_ant < -self.big_change:
                led.touch_flash()
                # Touch end: set event to publish this
                self.up_event.set()
                # Keep time of last 2 touch events
                previous_up = last_up
                last_up = time.ticks_ms()
                # See if this is a "double touch"
                if time.ticks_diff(last_up,previous_up)<DOUBLE_TOUCH_TIME:
                    self.double_event.set()
                    # 3 touch down in a row will yield 2 double events...
                # Wait for touchpad value to settle, and read again
                await asyncio.sleep_ms(MSEC_SETTLE)
            # See if this is a transition: hand touching the touchpad
            elif tpval - tpval_ant > self.big_change:
                # Touch down: show led, activate event, wait for signal to settle
                led.touch_start()
                self.down_event.set()
                print("TOUCH DOWN")
                await asyncio.sleep_ms(MSEC_SETTLE)
                
            tpval_ant = tpval

    def is_double_touch(self):
        if (
            time.ticks_diff(self.last_touch1, self.last_touch2)
            < DOUBLE_TOUCH_TIME
        ):
            return True
        return False
