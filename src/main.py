
# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# boot.py will copy main.py from romfs to root. That avoids
# having to freeze main.py. Only boot.py needs to be frozen.
# That allows an easier update of main.py

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


import sys, asyncio

# Establish sys.path to point to newest software.
# sys.path with romfs: ['', '.frozen', '/rom', '/rom/lib', '/lib']
# sys.path with flash: ['', '.frozen', '/lib']
def get_compiledate():
    try:
        from compiledate import compiledate
        cd = str(compiledate) # make copy
        del compiledate
        del sys.modules["compiledate"]
        return cd
    except ImportError:
        return "1900-01-01 00:00:00"
    
# Get frozen or romfs compile date
romfs_compiledate = get_compiledate()
sys.path[0] = "/software/mpy/" # replace "" with software/mpy
# Now get /software/mpy compile date
flash_compiledate = get_compiledate()
if romfs_compiledate >= flash_compiledate:
    # Use version in ROMFS, ignore /software folder and subfolders
    # Root is not needed, only main.py there, which is already running.
    # Old versions at /software should be deleted manually.
    sys.path.pop(0)

# Start up the software
import startup # type:ignore

