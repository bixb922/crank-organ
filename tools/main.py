
# (c) Copyright 2023-2026 Hermann Paul von Borries
# MIT License

# boot.py and main.py are both frozen. When distributing
# .bin files, this makes using romfs easier. boot.py and
# main.py are minimal. boot.py optimizes file system accesss.
# main.py shows led, sets CPU speed and establishes sys.path.

# First thing: turn on led
import led
led.hello()

# Web response time is nearly 3 times better with 240MHz than with 80MHz
# Garbage collection time: also nearly 3 times faster.
# But: 240 MHz consumes about 20 mA more than 80 MHz, that seems affordable.
# 20mA x 5V = 0.1W
import machine
machine.freq(240_000_000)

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

# Start up the software as async
from startup import start # type:ignore
asyncio.run(start())
# asyncio.run does not return.


