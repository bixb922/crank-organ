# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
# Blinks RGB (neopixel) LED.
# ESP32-S3 boards may have one of these.
#
from micropython import const
import asyncio
import neopixel
from machine import Pin

from minilog import getLogger

_LED_FILE = const("data/led.txt")

# 1=lowest, 255=highest
_VERY_LOW = const(4)
_LOW = const(8)
_MEDIUM = const(32)
_STRONG = const(128)
_VERY_STRONG = const(255)

class NoLED:
    # Using NoLED allows for a easy shutdown of the LED operation
    def __setitem__( self, key, value ):
        pass
    def write(self):
        pass

class BlinkingLed:
    def __init__(self):
        self.neopixel_led = NoLED()
        self.blink_setlist_task = None
        try: 
            p = get_led()        
            if p:
                self.neopixel_led = neopixel.NeoPixel(Pin(p), 1)

            self.off()
            self.blink_setlist_task = asyncio.create_task(self._blink_setlist_process())  
            self.problem_task = asyncio.create_task(self._problem_process())
        except Exception as e:
            getLogger.log_exc(__name__, e, "Could not initialize neopixel LED:" )
            # LED is now disabled but software should work ok with NoLed.


    # Simple (permanent) led on and off
    def on(self, color):
        self.neopixel_led[0] = color  # type:ignore
        self.neopixel_led.write()

    def off(self):
        self.on((0, 0, 0))

    # Problem encountered? run permanent task flashing red
    async def _problem_process(self):
        # Wait until asyncio is running
        await asyncio.sleep_ms(1000)
        
        while True:
            await asyncio.sleep_ms(1000)
            # Problem: error or exception entry in log
            if getLogger.get_error_count() > 0:
                # Replace this task with a blinking task
                self.problem_task = self._blink_background((_MEDIUM, 0, 0))
                # Don't blink for setlist empty anymore, could be confusing
                if self.blink_setlist_task:
                    self.blink_setlist_task.cancel() # type:ignore
                    self.blink_setlist_task = None
                # No way to exit red blinking, no need to test again.
                # But the blinking task created here could be superceded
                # by a sever error blinking....
                return

    # Starting phases, blue->green
    def starting(self, phase):
        self.on(
            (
                (0, 0, _VERY_LOW),
                (0, 0, _LOW),
                (0, _VERY_LOW, _VERY_LOW),
                (0, _LOW, 0),
            )[phase % 4]
        )

    # Setlist flashes
    def start_tune_flash(self):
        self._blink_background((0, _STRONG, 0), repeat=1)
    def shuffle_all_flash(self):
        self._blink_background((0, 0, _STRONG), repeat=1)
    def stop_tune_flash(self):
        self._blink_background((_MEDIUM, _STRONG, 0), repeat=1)

    def touch_start(self):
        color = (_LOW,_LOW,_LOW)
        self.on(color)

    def ack(self):
        # Acknowledge some action, such as reboot.
        self._blink_background(
            (
                (0, 0, _MEDIUM),
                (0, _MEDIUM, 0),
                (0, _MEDIUM, _MEDIUM),
                (_MEDIUM, 0, 0),
                (_MEDIUM, 0, _MEDIUM),
                (_MEDIUM, _MEDIUM, 0),
            ),
            timeon=200,
            timeoff=10,
            repeat=2,
        )

    def connected(self):
        # Create a background task to avoid
        # delaying caller
        self._blink_background((_LOW, _LOW, _LOW), repeat=6, timeoff=200)

    def heartbeat(self):
        self._blink_background((_VERY_LOW, _VERY_LOW, _VERY_LOW), repeat=1, timeon=50 )

    def short_problem(self):
        self._blink_background((_STRONG, _MEDIUM, 0), repeat=1, timeon=150)

    def severe(self):
        # Magenta on, no blink
        # Severe problem: unhandled exception caught
        # by global async error handler.
        if self.problem_task:
            # No more flashing for problem
            self.problem_task.cancel() # type:ignore    
        self.on((_MEDIUM, 0, _MEDIUM))

    def _blink_background(
        self, colors, repeat=1_000_000_000, timeon=50, timeoff=2000
    ):
        return asyncio.create_task(
                self._blink_process(colors, repeat, timeon, timeoff)
            )

    async def _blink_process(self, colors, repeat, timeon, timeoff):
        clist = colors
        if isinstance(colors[0], int):
            # Only one color specified
            clist = [colors]
        for _ in range(repeat):
            # Show all colors in succession
            for color in clist:
                self.on(color)
                await asyncio.sleep_ms(timeon)
            # now wait for next cycle
            self.off()
            await asyncio.sleep_ms(timeoff)

    def set_blink_setlist( self, value ):
        self.blink_setlist = value 

    async def _blink_setlist_process( self ):
        self.blink_setlist = False
        while True:
            await asyncio.sleep_ms(900)
            if self.blink_setlist:
                self.on( (0,0,_VERY_LOW ) )
                await asyncio.sleep_ms(80)
                self.off()

    def shutdown( self ):
        self.off()
        # Make sure noone can turn on the led again.
        self.neopixel_led = NoLED()

def set_led( pin ):
    # Caching pin makes this module decoupled from pinout
    # and led starts sooner. led.txt is only created if
    # the pin has changed and is different from the default 48.
    if get_led() != pin:
        # Write led.txt only if pin definition is different
        with open(_LED_FILE, "w") as file:
            file.write(str(pin))

def get_led():
    try:
        with open(_LED_FILE) as file:
            return int(file.read())
    except: 
        return 48
