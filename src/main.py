# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# First thing: turn on led
from machine import Pin, freq
from neopixel import NeoPixel
led = NeoPixel(Pin(48), 1)
led[0] = (0, 0, 8)  # type:ignore
led.write()

# Web response time is nearly 3 times better with 240MHz than with 80MHz
# Garbage collection time: also nearly 3 times faster.
# Startup until controller.clap(): 7 sec with 240MHz, 19sec with 80MHz
# But: 240 MHz consumes about 20 mA more than 80 MHz, that seems affordable.
# 20mA x 5V = 0.1W
freq(240_000_000) # machine.freq()

import os
import sys
import errno

# Mount with more appropriate file system parameters
# lookahead must increase to offset for the size of the flash.
# Optimal value of lookahead is the number of blocks of the flash/8
# since then the complete bitmap of free blocks is in RAM.
# Overhead setting to a large value is low.
# 16Mb = 4096 blocks/8 bits per byte=512 bytes for lookahead size, 
# although it could be a bit lower since 
# not all 16 MB are really available.
# Largest impact is readsize=. Impact of lookahead= is low.
# Mount is done in boot.py, since that speeds up mpremote too,

# sys.path with romfs: ['', '.frozen', '/rom', '/rom/lib', '/lib']
# sys.path with flash: ['', '.frozen', '/lib']
try:
    # Put this folder at beginning to enable incremental update
    # during development.
    open("software/mpy").close()
    # No folder software/mpy. don't add to path.
    # Remove root to make boot slightly faster
    if sys.path[0] == "":
        sys.path.pop(0)
except OSError as e:
    if e.errno == errno.EISDIR:
        sys.path[0] = "/software/mpy"


# Startup from flash filesystem (software/mpy):
# MPY folder has a total of 41 mpy files = 123_173 bytes
#    Total startup time (without main, until asyncio ready) 3236 msec
#    Memory used at startup 216288
#    gc.collect() times around 38 ms
# Same with romfs (mpy files only):
# Image size is 123_998 bytes 
# ROMFS0 partition has size 131_072 bytes (32 blocks of 4096 bytes each)
#    Total startup time (without main, until asyncio ready) 1380 msec
#    Memory used at startup 124000 to 135000 bytes
#    gc.collect() times around 10 ms
#    Image size is the sum of MPY files with an overhead of 0.6%
#
# Time to deploy mpy+static
# Image size is 221592 bytes, but with data compressed = 203704 bytes
# ROMFS0 partition has size 262144 bytes (64 blocks of 4096 bytes each)
# mpremote romfs deploy *.gz + *.mpy 0.79s user 0.40s system 6% cpu 18.754 total
#
# It's not a good idea to import main in _boot.py, that makes software
# not interruptible (i.e. no ctrl-C). File main.py must be on flash root.

# Start up the software
import startup # type:ignore
