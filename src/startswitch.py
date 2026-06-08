# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
# start switch asyncio driver, detects button down event in background
# and triggers events defined by registering.
from machine import Pin

from startbase import StartBase

class StartSwitch(StartBase):
    def init(self, gpio_pin ):
        # return function to read pin value
        return Pin(gpio_pin, Pin.IN, Pin.PULL_UP).value
        
    @staticmethod
    def _transition_up(val, last_val):
        return val == 1 and last_val == 0
    
    @staticmethod
    def _transition_down(val, last_val):
        return val == 0 and last_val == 1
