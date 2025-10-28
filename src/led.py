# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
# Blinks RGB (neopixel) LED.
# ESP32-S3 boards may have one of these.
#
from micropython import const
import asyncio
import neopixel
import machine

# if __name__ == "__main__":
#    sys.path.append("software/mpy")

LED_FILE = "data/led.txt"

# 1=lowest, 255=highest
VERY_LOW = const(4)
LOW = const(8)
MEDIUM = const(32)
STRONG = const(128)
VERY_STRONG = const(255)

class NoLED:
    def __setitem__( self, key, value ):
        pass
    def write(self):
        pass

class BlinkingLed:
    def __init__(self):
        p = get_led()        
        if p:
            self.neopixel_led = neopixel.NeoPixel(machine.Pin(p), 1)
        else:
            # Using NoLED allows for a easy shutdown of the LED operation
            self.neopixel_led = NoLED()

        self.off()

        # Get a logger to get error count
        self.logger = None

        self.setlist = None # We don't know the setlist yet, too early
        
        self.problem_task = asyncio.create_task(self._problem_process())
        self.blink_setlist_task = asyncio.create_task(self._blink_setlist_process())  

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
        # minilog is needed to get error count to blink red if a problem occurred
        import minilog
        self.logger = minilog.getLogger(__name__)
            
        while True:
            # Problem: error or exception entry in log
            if self.logger.get_error_count() > 0:
                # Replace this task with a blinking task
                self.problem_task = self._blink_background((MEDIUM, 0, 0))
                # Don't blink for setlist empty anymore, could be confusing
                if self.blink_setlist:
                    self.blink_setlist_task.cancel() # type:ignore
                    self.blink_setlist_task = None
                # No way to exit red blinking, no need to test again.
                # But the blinking task created here could be superceded
                # by a sever error blinking....
                return
            await asyncio.sleep_ms(1000)

    # Starting phases, blue->green
    def starting(self, phase):
        # Shades of green
        self.on(
            (
                (0, 0, VERY_LOW),
                (0, 0, LOW),
                (0, VERY_LOW, VERY_LOW),
                (0, LOW, 0),
            )[phase % 4]
        )

    # Setlist flashes
    def start_tune_flash(self):
        self._blink_background((0, STRONG, 0), repeat=1)
    def shuffle_all_flash(self):
        self._blink_background((0, 0, STRONG), repeat=1)
    def stop_tune_flash(self):
        self._blink_background((MEDIUM, STRONG, 0), repeat=1)

    def touch_start(self):
        color = (LOW,LOW,LOW)
        self.on(color)

    def ack(self):
        # Acknowledge some action, such as reboot.
        self._blink_background(
            (
                (0, 0, MEDIUM),
                (0, MEDIUM, 0),
                (0, MEDIUM, MEDIUM),
                (MEDIUM, 0, 0),
                (MEDIUM, 0, MEDIUM),
                (MEDIUM, MEDIUM, 0),
            ),
            timeon=200,
            timeoff=10,
            repeat=2,
        )

    def connected(self):
        # Create a background task to avoid
        # delaying caller
        self._blink_background((LOW, LOW, LOW), repeat=6, timeoff=200)

    def heartbeat(self):
        self._blink_background((VERY_LOW, VERY_LOW, VERY_LOW), repeat=1, timeon=50 )

    def short_problem(self):
        self._blink_background((STRONG, MEDIUM, 0), repeat=1, timeon=150)

    def severe(self):
        # Magenta on, no blink
        # Severe problem: unhandled exception caught
        # by global async error handler.
        if self.problem_task:
            # No more flashing for problem
            self.problem_task.cancel() # type:ignore    
        self.on((MEDIUM, 0, MEDIUM))

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
                self.on( (0,0,VERY_LOW ) )
                await asyncio.sleep_ms(80)
                self.off()

    def shutdown( self ):
        self.off()
        # Make sure noone can turn on the led again.
        self.neopixel_led = NoLED()

def set_led( pin ):
    # Caching pin makes this module decoupled from pinout
    # and led starts sooner. led.txt is only written if
    # the pin is changes and is different from the default 48.
    if get_led() != pin:
        # Write led.txt only if pin definition is different
        with open(LED_FILE, "w") as file:
            file.write(str(pin))

def get_led():
    try:
        with open(LED_FILE) as file:
            return int(file.read())
    except: 
        return 48
