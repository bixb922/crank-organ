# (c) 2023 Hermann Paul von Borries
# MIT License
# First thing: show we are starting with the led, if installed
  
import machine
import gc

# Web response time is nearly 3 times better with 240MHz than with 80MHz
# Garbage collection time: also nearly 3 times faster.
# Startup until solenoids.clap(): 7 sec with 240MHz, 19sec with 80MHz
# But: 240 MHz consumes about 20 mA more than 80 MHz, seems affordable.
# 20mA x 5V = 0.1W
machine.freq(240_000_000) 

import sys
import os
import asyncio
import time

# Create data folder if not there
# Data that changes in time is stored here: battery info
# setlist, logs, timezone information, pinout information. Create before importing minilog, config, battery, timezone.
try:
    os.mkdir( "data" )
except OSError:
    pass

import scheduler # 0
import timezone # 2
from minilog import getLogger # 3
import compiledate # 0
import fileops # 3
from config import config # 5
import wifimanager # 6
import mcp23017 # 0
import midi # 0
import pinout # 9
from led import led # config, fileops, late:config, late:timezone, mcp23017, midi, minilog, pinout, re, scheduler, timezone
led.starting(0) 
import touchpad # 6
import tachometer # 10
import history # 6
from solenoid import solenoid # 10
led.starting( 1 )
import tunemanager # 9
import battery # 12
import zcr # 0
import organtuner # 14
led.starting(2)
import umidiparser # 1
import player # 17
import setlist # 20
#import tinyweb # 0
led.starting(3)
from microdot_asyncio import Microdot
import mdwebserver as webserver # 26
import poweroff # 28


_logger = getLogger( __name__ )
_logger.debug("imports done")

# Global asyncio exception handler
def _handle_exception(loop, context):
    print("main._handle_exception: unhandled asyncio exception", context )
    # Will catch any unhandled exception of asyncio tasks.
    _logger.exc(  context["exception"], "asyncio global exception handler" )
    led.severe()
    solenoid.all_notes_off()
    sys.exit()  # Drastic: terminate/reinit

# Global background garbage collector. Use scheduler
# to avoid interfering with the high priority task: the MIDI player
async def background_garbage_collector():
    # With MicroPython 1.21 and later, gc.collect() is not critical anymore
    # But I'll still keep the code.
    while True:
        await asyncio.sleep_ms(3000)
		# gc is best if not delayed more than a few seconds
        try:
            async with scheduler.RequestSlice(
                "gc.collect", config.max_gc_time, 5000):
                gc.collect()
        except RuntimeError:
            # IF timeout, collect garbage anyhow
            # No good to accumulate pending gc
            gc.collect()
    

# idle() measures asyncio responsiveness.
#async def idle():
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
    await asyncio.sleep_ms( 100 )
    await solenoid.clap(8)
    led.off()

       
async def main(): 
    #  Establish global exception handler for asyncio
    asyncio.get_event_loop( ).set_exception_handler( _handle_exception )
                    
    gc.collect()
    scheduler.run_always()
    
    _logger.debug("Starting asyncio loop" )
    await asyncio.gather( webserver.run_webserver(),
                          background_garbage_collector(),
                          signal_ready(),
                          # idle() # to measure async response
                        ) 
asyncio.run( main() )
