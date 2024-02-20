print("Go!")
import os
# Mount with more appropriate file system parameters
# lookahead must increase to offset for the size of the flash.
# Optimal value of lookahead is the number of blocks of the flash/8
# since then the complete bitmap of free blocks is in RAM.
# Overhead setting to a large value is low.
# 16Mb = 4096 blocks/8=512

os.umount("/")
readsize, progsize, lookahead =(1024,128,512)
os.mount(os.VfsLfs2(bdev,readsize=readsize,progsize=progsize,lookahead=lookahead),"/")
print(f"VfsLfs2 mount with {readsize=}, {progsize=},{lookahead=}")
import machine
import sys

# Web response time is nearly 3 times better with 240MHz than with 80MHz
# Garbage collection time: also nearly 3 times faster.
# Startup until solenoids.clap(): 7 sec with 240MHz, 19sec with 80MHz
# But: 240 MHz consumes about 20 mA more than 80 MHz, seems affordable.
# 20mA x 5V = 0.1W
machine.freq(240_000_000)

from neopixel import NeoPixel

led = NeoPixel(machine.Pin(48), 1)
led[0] = (0, 0, 8)
led.write()

sys.path.insert(0, '/software/mpy' )
#try:
#    open("/software/mpy/startup.mpy").close()
#    sys.path = ["/software/mpy", ".frozen", "/lib"]
#except OSError:
#    sys.path = [".frozen", "/lib"] 

import startup # noqa
