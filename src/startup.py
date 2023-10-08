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
# setlist, logs. Create before importing minilog, config, battery
try:
    os.mkdir( "data" )
except OSError:
    pass

import minilog
_logger = minilog.getLogger( __name__ )

import scheduler
import config
import pinout
import led
led.starting( 0 )
  
import wifimanager
import solenoid
import battery
import tunelist
import tachometer
import touchpad
import umidiparser
import modes
import player
import setlist
import webserver



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
        async with scheduler.RequestSlice("gc.collect", config.max_gc_time, 2500):
            gc.collect()

# async def idle():
# idle() measures asyncio responsiveness.
##    import time
##    max_iterations = 0
##    while True:
##        max_async_block = 0
##        t0 = time.ticks_ms()
##        t1 = t0
##        iterations = 0
##        while True:
##            await asyncio.sleep(0)
##            t = time.ticks_ms()
##            if time.ticks_diff( t, t0 ) > 1000: # Loop for 1 second
##                break
##            dt = time.ticks_diff( t, t1 )
##            max_async_block = max( dt, max_async_block )
##            t1 = t
##            iterations += 1
##        dt = time.ticks_diff( t, t0 )
##        max_iterations = max( iterations, max_iterations )
##        if max_async_block > 30:
##            iterations_per_sec = iterations/dt*1000
##            _logger.timeline(f"delay {max_async_block} it/sec {iterations_per_sec:.0f}")

async def signal_ready():
    # Tell user system ready
    await asyncio.sleep_ms( 100 )
    await solenoid.clap(8)
    led.operating()

       
async def main():
    #  Establish global exception handler for asyncio
    asyncio.get_event_loop().set_exception_handler(_handle_exception)
                    
    # Turn on neopixel if installed
    led.starting( 1 )
    gc.collect()

    _logger.debug("Starting asyncio loop" )
    await asyncio.gather( webserver.run_webserver(),
                          background_garbage_collector(),
                          signal_ready()
                        ) 

asyncio.run( main() )
