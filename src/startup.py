# (c) 2023 Hermann Paul von Borries
# MIT License
# First thing: show we are starting with the led, if installed

import time
startup_time = time.ticks_ms()
import machine
import gc
import sys
import os
import asyncio
import network
import json

# Create data folder if not there
# Data that changes in time is stored here: battery info
# setlist, logs, timezone information, pinout information. Create before importing minilog, config, battery, timezone.
try:
    os.mkdir("data")
    os.mkdir("tunelib")
except OSError:
    pass

gc.collect()
last_alloc = gc.mem_alloc()
lastt = time.ticks_ms()
#print("initial allocation", last_alloc)
def reportmem(s):
    return # NO REPORT MEM
    global last_alloc, lastt
    size = 0
    #try:
    #    size = os.stat("software/mpy/"+s+".mpy")[6]
    #except OSError:
    #        size = 0
    gc.collect()
    alloc = gc.mem_alloc()
    newt = time.ticks_ms()
    dt = time.ticks_diff(newt,lastt)
    print(s,alloc-last_alloc,"bytes", "alloc",alloc,"time:", dt)
    last_alloc = alloc
    lastt = newt
    
    
 #Startup time con hard reset.
 #9 seg con todo en software/mpy, ese folder de primero en sys.path
 #5 seg con sys.path=['.frozen', '/lib'] y similar con ["/lib", ".frozen"]
 #5 seg con sys.path=['.frozen', '/lib'] y sin archivos de respaldo en /data
 #=> 5 segundos hasta desde boot hasta clap (medido incluso antes de ntptime)
import scheduler
reportmem("scheduler")
from timezone import timezone
reportmem("timezone")
from minilog import getLogger
timezone.setLogger(getLogger)
reportmem("minilog")

 
import compiledate
import fileops  # 3
reportmem("fileops")
from config import config  # 5
reportmem("config")
import wifimanager  # 6
reportmem("wifimanager")
import mcp23017  # 0
reportmem("mcp23017")
import midi  # 0
reportmem("midi")
import pinout  # 9
reportmem("pinout")
from led import led
reportmem("led")
led.starting(0)
from solenoid import solenoid  # 10
reportmem("solenoid")
led.starting(1)
import battery  # 12
reportmem("battery")
#>>>import zcr  # 0
#>>>reportmem("zcr")
import organtuner  # 14
reportmem("organtuner")
import touchpad  # 6
reportmem("touchpad")
import tachometer  # 10
reportmem("tachometer")
import history  # 6
reportmem("history")
import tunemanager  # 9
reportmem("tunemanager")
led.starting(2)
import umidiparser  # 1
reportmem("umidiparser")
from player import player  # 17
reportmem("player")
from setlist import setlist  # 20
reportmem("setlist")
led.set_setlist(setlist)
led.starting(3)
from microdot_asyncio import Microdot
reportmem("microdot")
import webserver  # 26
reportmem("webserver")
import poweroff  # 28
reportmem("poweroff")

try:
    import mcserver
    reportmem("mcserver")
except ImportError:
    # No impact if mcserver not present.
    pass

_logger = getLogger(__name__)
_logger.debug("imports done")


# Global asyncio exception handler
def _handle_exception(loop, context):
    print("main._handle_exception: unhandled asyncio exception", context)
    # Will catch any unhandled exception of asyncio tasks.
    _logger.exc(context["exception"], "asyncio global exception handler")
    led.severe()
    solenoid.all_notes_off()
    sys.exit()  # Drastic: terminate/reinit


# Global background garbage collector. Use scheduler
# to avoid interfering with the high priority task: the MIDI player
async def background_garbage_collector():
    # With MicroPython 1.21 and later, gc.collect() is not critical anymore
    # But I'll still keep the code.
    while True:
        await asyncio.sleep_ms(2000)
        # gc is best if not delayed more than a few seconds
        try:
            async with scheduler.RequestSlice(
                "gc.collect", config.max_gc_time, 5000
            ):
                gc.collect()
        except RuntimeError:
            # IF timeout, collect garbage anyhow
            # No good to accumulate pending gc
            gc.collect()


# idle() measures asyncio responsiveness.
# async def idle():
#    import time
#    max_iterations = 0
#    while True:
#        max_async_block = 0
#        t0 = time.ticks_ms()
#        t1 = t0
#        iterations = 0
#        while True:
#            await asyncio.sleep_ms(0)
#            t = time.ticks_ms()
#            dt = time.ticks_diff( t, t1 )
#            max_async_block = max( dt, max_async_block )
#            if time.ticks_diff( t, t0 ) > 1000:
#                # Loop for about 1 second
#                break
#            t1 = t
#            iterations += 1
#        dt = time.ticks_diff( t, t0 )
#        max_iterations = max( iterations, max_iterations )
#        if max_async_block >= 0:
#            iterations_per_sec = iterations/dt*1000
#            print(f"max async block {max_async_block} it/sec {iterations_per_sec:.0f} {dt=}")


async def signal_ready():
    # Tell user system ready
    await asyncio.sleep_ms(100)
    await solenoid.clap(8)
    led.off()
    dt = time.ticks_diff(time.ticks_ms(), startup_time)
    print(f"Total startup time (without main, until asyncio ready) {dt} msec")


async def main():
    #  Establish global exception handler for asyncio
    asyncio.get_event_loop().set_exception_handler(_handle_exception)

    gc.collect()
    scheduler.run_always()

    _logger.debug("Starting asyncio loop")
    await asyncio.gather(
        webserver.run_webserver(),
        background_garbage_collector(),
        signal_ready(),
        # idle() # to measure async response
    )


asyncio.run(main())
