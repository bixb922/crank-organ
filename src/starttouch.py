# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
# Touchpad asyncio driver, detects button down event in background
# and triggers events defined by registering.
from machine import Pin, TouchPad

from drehorgel import config
from startbase import StartBase

class StartTouch(StartBase):
    def init(self, gpio_pin ):
        # return function to read touchpad value
        return TouchPad( Pin(gpio_pin) ).read
        
    @staticmethod
    def _transition_up(val, last_val):
        return (val-last_val)<(-config.touchpad_big_change)
    
    @staticmethod
    def _transition_down(val, last_val):
        return (val-last_val)>config.touchpad_big_change

