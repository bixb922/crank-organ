
# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# boot.py and main.py are both frozen. When distributing
# .bin files, this makes using romfs easier. boot.py and
# main.py are minimal. boot.py optimizes file system accesss.
# main.py establishes sys.path.

# First thing: turn on led
from machine import Pin, freq
from neopixel import NeoPixel
led = NeoPixel(Pin(48), 1)
led[0] = (0, 0, 8)
led.write()

# Web response time is nearly 3 times better with 240MHz than with 80MHz
# Garbage collection time: also nearly 3 times faster.
# But: 240 MHz consumes about 20 mA more than 80 MHz, that seems affordable.
# 20mA x 5V = 0.1W
freq(240_000_000) # machine.freq()


import sys, asyncio, errno

# Establish sys.path to point to newest software.
# sys.path with romfs: ['', '.frozen', '/rom', '/rom/lib', '/lib']
# sys.path with flash: ['', '.frozen', '/lib']
sys.path.pop(0) # "" not needed
try:
    open("software/mpy").close()
except OSError as e:
    if e.errno == errno.EISDIR:
        # Use software/mpy before romfs but after .frozen
        sys.path.insert( 1,  "/software/mpy/" )
        # webserver.py also checks "/software/static" before romfs.
print(f"{sys.path=}")   

# Start up the software
from startup import start # type:ignore
asyncio.run(start())
# Does not return.


