# (c) 2023 Hermann Paul von Borries
# MIT License
# First thing: show we are starting with the led, if installed

import time
startup_time = time.ticks_ms()

import gc
import sys
import os
import asyncio

# Create data folder if not there
# Data that changes in time is stored here: battery info
# setlist, logs, timezone information, pinout information. Create before importing minilog, config, battery, timezone.
try:
    os.mkdir("data")
    os.mkdir("tunelib")
except OSError:
    pass

# Startup < 4 sec when in flash, less if frozen.
import scheduler
from timezone import timezone
from minilog import getLogger
timezone.setLogger(getLogger)
from config import config
from led import led
# Start wifimanager as early as possible, so the connections are
# in progress while doing the rest of the imports
import wifimanager 
led.starting(0)
from solenoid import solenoid 
led.starting(1)
led.starting(2)
from setlist import setlist
led.set_setlist(setlist)
led.starting(3)
import webserver    


try:
    import mcserver
except ImportError:
    # No impact if mcserver not present.
    pass

_logger = getLogger(__name__)
# to install aioprof:
# mpremote mip install https://gitlab.com/alelec/aioprof/-/raw/main/aioprof.py
# to install aiorepl:
# mpremote mip install aiorepl
try:
    # For debugging and testing, enable only if present.
    import aiorepl
    repl = asyncio.create_task(aiorepl.task())
    print("aiorepl enabled")
except ImportError:
    pass

# Global asyncio exception handler
def _handle_exception(loop, context):
    print("main._handle_exception: unhandled asyncio exception", context)
    # Will catch any unhandled exception of asyncio tasks.
    _logger.exc(context["exception"], "asyncio global exception handler")
    led.severe()
    solenoid.all_notes_off()
    # >>> consider starting FTP and remain waiting.
    # >>> cancel all asyncio tasks?
    last_resort()

def last_resort():
    print("unrecoverable error, starting uftpd...")
    # let's hope the wifi is up at this point...
    import uftpd
    while True:
        time.sleep(1000)

# Global background garbage collector. 
# Use the scheduler
# to avoid interfering with the high priority task: the MIDI player
async def background_garbage_collector():
    # With MicroPython 1.21 and later, gc.collect() is not critical anymore
    # But I'll still keep the code. Now gc.collect() duration depends on
    # RAM allocated and not total RAM size.
    while True:
        await asyncio.sleep_ms(2000)
        # gc is best if not delayed more than a few seconds
        try:
            async with scheduler.RequestSlice(
                "gc.collect", config.max_gc_time, 5000
            ):
                gc.collect()
        except RuntimeError:
            # If RequestSlice times out, collect garbage anyhow
            # No good to accumulate pending gc
            gc.collect()

async def report_profile():
    # Report profile every 30 seconds for debugging/optimizing
    try:
        import aioprof
    except ImportError:
        return
    aioprof.inject()
    print("aioprof enabled")
    while True:
        await asyncio.sleep(30)
        aioprof.report()
        
        
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
        report_profile(),
        # idle() # to measure async response
    )


asyncio.run(main())
