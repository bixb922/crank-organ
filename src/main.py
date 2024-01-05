print("Go!")

from machine import Pin, freq
import sys

# Web response time is nearly 3 times better with 240MHz than with 80MHz
# Garbage collection time: also nearly 3 times faster.
# Startup until solenoids.clap(): 7 sec with 240MHz, 19sec with 80MHz
# But: 240 MHz consumes about 20 mA more than 80 MHz, seems affordable.
# 20mA x 5V = 0.1W
freq(240_000_000)

from neopixel import NeoPixel

led = NeoPixel(Pin(48), 1)
led[0] = (0, 0, 8)
led.write()

# sys.path.insert(0, '/software/mpy' )
try:
    open("/software/mpy/startup.mpy").close()
    sys.path = ["/software/mpy", ".frozen", "/lib"]
except:
    sys.path = [".frozen", "/lib"] 

import startup
