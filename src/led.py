# (c) 2023 Hermann Paul von Borries
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

class BlinkingLed:
    def __init__(self):
        self.neopixel_led = None
        p = get_led()
        if p:
            self.neopixel_led = neopixel.NeoPixel(machine.Pin(p), 1)
            self.off()

            self.logger = None
            self.setlist = None # We don't know the setlist yet, too early
            
            self.problem_task = asyncio.create_task(self._problem_process())
           

    # Simple (permanent) led on and off
    def on(self, color):
        if self.neopixel_led:
            self.neopixel_led[0] = color
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
        if self.neopixel_led:
            
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
            self.problem_task.cancel()
        self.on((MEDIUM, 0, MEDIUM))

    def _blink_background(
        self, colors, repeat=1_000_000_000, timeon=50, timeoff=2000
    ):
        if self.neopixel_led:
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

def set_led( pin ):
    # Caching pin makes this module decoupled from pinout
    # and led starts sooner
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
