# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

from time import ticks_ms, ticks_diff 
startup_time = ticks_ms()

import gc
import asyncio

# Create folders if not there
# Data that changes in time is stored here: battery info
# setlist, logs, timezone information, pinout information. Create before importing minilog, config, battery, timezone.
# Startup about 4.5 sec when in flash, less if frozen.
import scheduler

# First thing: initialize led and get turn it on
import drehorgel
drehorgel.init_led()
led = drehorgel.led

led.starting(0)


# First ensure all mandatory folders are there.
drehorgel.init_fileops()

# And get the time/timezone/ntp process going in background,
# the timezone object is needed for logger, and most modules
# require logger
drehorgel.init_timezone()
import minilog 
_logger = minilog.getLogger(__name__)


# To install aiorepl:
# mpremote mip install aiorepl
# aiorepl will be activated automatically if present
def start_aiorepl():
    try:
        # For debugging and testing, enable automatically if aiorepl present.
        import aiorepl # type:ignore
        asyncio.create_task(aiorepl.task())
        print("aiorepl enabled")
    except ImportError:
        pass

# Global asyncio exception handler
def _handle_exception(loop, context):
    print("main._handle_exception: unhandled asyncio exception", context)
    # Will catch any unhandled exception of asyncio tasks.
    _logger.exc(context["exception"], "asyncio global exception handler")
    led.severe()
    from drehorgel import controller
    controller.all_notes_off()
    # exit to REPL

# To install aioprof:
# mpremote mip install https://gitlab.com/alelec/aioprof/-/raw/main/aioprof.py
# aioprof will be activated automatically if present
async def do_aioprof():
    # Report profile every 30 seconds for debugging/optimizing
    # if aioprof is installed
    try:
        import aioprof # type:ignore
    except ImportError:
        return
    aioprof.inject()
    print("aioprof enabled")
    while True:
        await asyncio.sleep(30)
        aioprof.report()
        
def start_mcserver():
    # Start communication task with server on internet
    # but only if installed.
    try:
        import mcserver # type:ignore
    except ImportError:
        # No impact if mcserver not present.
        pass
    except Exception as e:
        print("Exception importing mcserver", e)



async def signal_ready( controller ):
    t1 = ticks_ms()
    gc.collect()
    gc_t = ticks_diff( ticks_ms(), t1 )
    start_dt = ticks_diff(t1, startup_time)
    alloc = gc.mem_alloc()
    
    controller.all_notes_off()
    print(f">>>Total startup time (without main, until asyncio ready) {start_dt} msec")
    print(f">>>Memory used at startup {alloc} gc={gc_t} msec")
    # Tell user system ready
    await controller.clap(8)
    led.off()


async def main():
    #  Establish global exception handler for asyncio
    asyncio.get_event_loop().set_exception_handler(_handle_exception)

    # Pass getLogger to timezone... it can't import minilog
    # that would be circular imports.
    drehorgel.timezone.setLogger(minilog.getLogger)
    # Get configuration
    drehorgel.init_config()

    # Start wifimanager as early as possible, so the connections are
    # in progress while doing the rest of the imports, give
    # it a little time to start. WiFi does it's work in parallel
    # so when initialization is finished, WiFi most probably is
    # already connected
    await drehorgel.init_wifimanager()

    # Start asyncio profiler and asyncio repl if installed
    start_aiorepl()

    scheduler.run_always()
    drehorgel.init()
    import webserver 

    start_mcserver()   

    led.starting(3)

    _logger.debug("Starting asyncio loop")
    await asyncio.gather(
        webserver.run_webserver(),
        scheduler.background_garbage_collector(),
        signal_ready(drehorgel.controller),
        #>>>do_aioprof() # only works if aioprof installed.
    ) # type:ignore

asyncio.run(main())

