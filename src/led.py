# (c) 2023 Hermann Paul von Borries
# MIT License
# Blinks RGB (neopixel) LED.
# ESP32-S3 boards may have one of these.
#
import asyncio
import neopixel
import machine
#>>> flash led light blue while there is no setlist
#>>> feedback for button: always white

# if __name__ == "__main__":
#    sys.path.append("software/mpy")

from pinout import gpio
from minilog import getLogger

# 1=lowest, 255=highest
VERY_LOW = const(4)
LOW = const(8)
MEDIUM = 32
STRONG = const(128)
VERY_STRONG = const(255)


class BlinkingLed:
    def __init__(self, p):
        self.neopixel_led = None
        if not p:
            # No LED task is needed
            return

        self.neopixel_led = neopixel.NeoPixel(machine.Pin(p), 1)
        self.off()

        self.logger = getLogger(__name__)
        self.setlist = None # We don't know the setlist yet, too early
        
        self.problem_task = asyncio.create_task(self._problem_process())
        self.logger.debug("init done")

    # Simple (permanent) led on and off
    def on(self, color):
        if not self.neopixel_led:
            return
        self.neopixel_led[0] = color
        self.neopixel_led.write()

    def off(self):
        self.on((0, 0, 0))

    # Problem encountered? run permanent task flashing red
    async def _problem_process(self):
        if not self.neopixel_led:
            return
        while True:
            # Problem: error or exception entry in log
            if self.logger.get_error_count() > 0:
                self.problem_task = self._blink_background((MEDIUM, 0, 0))
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

    # Touch start and touch flash
    def touch_flash(self):
        self._blink_background((STRONG, STRONG, STRONG), repeat=1)

    def set_setlist(self,setlist):
        # This avoids doing late import
        self.setlist = setlist
        self_setlist_process = asyncio.create_task( self.setlist_blinker() )
        
    async def setlist_blinker(self):
        # Blink light blue-green while setlist is empty
        while True:
            if self.setlist.isempty():
                self.on( (0,LOW,MEDIUM) )
                await asyncio.sleep_ms(40) 
            self.off()
            # Period different from other blinks, so interference will be low
            # Use number based on the best random number: 37.
            await asyncio.sleep_ms(3700)
            
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
        self._blink_background(
            ((0, MEDIUM, 0), (0, 0, MEDIUM)), repeat=1, timeon=100, timeoff=50
        )

    def short_problem(self):
        self._blink_background((STRONG, MEDIUM, 0), repeat=1, timeon=150)

    def severe(self):
        # Magenta on, no blink
        # Severe problem: unhandled exception caught
        # by global async error handler.
        if self.problem_task:
            # No more flashing for problem
            self.problem_task.cancel()
        self.on((MEDIUM, 0, MEDIUM))

    def _blink_background(
        self, colors, repeat=1_000_000_000, timeon=50, timeoff=2000
    ):
        if not self.neopixel_led:
            return
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


led = BlinkingLed(gpio.neopixel_pin)

# if __name__ == "__main__":
#    async def test():
#        print("led blue")
#        led.on((0,0,32))
#        await asyncio.sleep(1)
#
#        print("led touch start")
#        led.touch_start()
#        await asyncio.sleep(0.5)
#
#        print("led touch flash")
#        led.touch_flash()
#        await asyncio.sleep(1)
#
#        for _ in range(3):
#            print("led short problem")
#            led.short_problem()
#            await asyncio.sleep(1)
#
#        for _ in range(3):
#            print("led heartbeat")
#            led.heartbeat()
#            await asyncio.sleep(1)
#
#        print("led connected")
#        led.connected()
#        await asyncio.sleep(1)
#
#        print("led ack")
#        led.ack()
#        await asyncio.sleep(1)
#
#        print("led problem")
#        # simulate problem
#        led.logger.baselogger.error_count = 1
#        await asyncio.sleep(10)
#
#        print("led severe")
#        led.severe()
#        await asyncio.sleep(1)
#        led.off()
#
#    asyncio.run( test() )
