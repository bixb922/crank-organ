# (c) 2023 Hermann Paul von Borries
# MIT License
# Touchpad asyncio driver, detects button down event in backbround
# and triggers event defined by set_release_event.
import machine
import asyncio
import time

from config import config
from led import led

MSEC_BETWEEN_SAMPLES = const(100)
MSEC_SETTLE = const(50)
DOUBLE_TOUCH_TIME = const(1000)


class TouchButton:
    def __init__(self, gpio_pin):
        # Only release event, no touch event
        # self.release_event is redefined later by set_release_event.
        self.release_event = None
        self.big_change = int(config.get_int("touchpad_big_change", 10000))
        self.last_touch1 = time.ticks_ms()
        self.last_touch2 = time.ticks_add(
            self.last_touch1, -DOUBLE_TOUCH_TIME * 2
        )

        if gpio_pin:
            self.gpio_pin = gpio_pin
            self.tp = machine.TouchPad(machine.Pin(gpio_pin))
            self.task = asyncio.create_task(self.tp_process())
        # If no gpio_pin, don't assign button, don't create task.
        # Event will never get set.

    def set_release_event(self, ev):
        self.release_event = ev

    async def tp_process(self):
        await asyncio.sleep(1)
        tpval_ant = self.tp.read()
        while True:
            await asyncio.sleep_ms(MSEC_BETWEEN_SAMPLES)
            tpval = self.tp.read()
            if tpval - tpval_ant < -self.big_change:
                # Touch end: set event to publish this
                # Also: see if this is a "double touch"
                led.touch_flash()
                if self.release_event:
                    self.release_event.set()
                    # Keep time of last 2 touch events
                    self.last_touch2 = self.last_touch1
                    self.last_touch1 = time.ticks_ms()
                # Wait for touchpad value to settle, and read again
                await asyncio.sleep_ms(MSEC_SETTLE)
                tpval = self.tp.read()
            elif tpval - tpval_ant > self.big_change:
                # Touch start: show led
                led.touch_start()

            tpval_ant = tpval

    def is_double_touch(self):
        if (
            time.ticks_diff(self.last_touch1, self.last_touch2)
            < DOUBLE_TOUCH_TIME
        ):
            return True
        return False
