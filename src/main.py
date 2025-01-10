# (c) 2023 Hermann Paul von Borries
# MIT License

#print("Go!")
# First thing: turn on led
from machine import Pin, freq
from neopixel import NeoPixel
led = NeoPixel(Pin(48), 1)
led[0] = (0, 0, 8)
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

os.umount("/")
readsize = 1024
progsize = 128
lookahead = 512
os.mount(os.VfsLfs2(bdev,readsize=readsize,progsize=progsize,lookahead=lookahead),"/") # type:ignore
print(f"VfsLfs2 mounted with {readsize=}, {progsize=}, {lookahead=}")

# Path element order makes a difference of 1.6 sec in startup time
sys.path = [ ".frozen", "/lib"]
try:
    open("/software/mpy").close()
except OSError as e:
    if e.errno == errno.EISDIR:
        # This order allows to override frozen modules
        sys.path = ["/software/mpy",  ".frozen", "/lib" ]

import startup # type: ignore
