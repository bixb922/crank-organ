# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

from time import ticks_ms, ticks_diff 
startup_time = ticks_ms()

import gc
import asyncio

try:
    import aioprof # type:ignore
    aioprof.enable()
    # aioprof.inject() sometimes leaves asyncio in confusion. Don't.
except:
    pass

# Startup about 4.5 sec when in flash, less if frozen.
import scheduler
import drehorgel
from minilog import getLogger


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
    _led.severe()
    from drehorgel import controller
    controller.all_notes_off()
    # exit to REPL

# To install aioprof:
# mpremote mip install https://gitlab.com/alelec/aioprof/-/raw/main/aioprof.py
# aioprof will be activated automatically if present
# Patched aioprof.py in def send():
# process only: if t_name != "do_aioprof"
# and cleanup: t_name = t_name.split("'")[1]
async def do_aioprof():
    if "aioprof" not in globals():
        return
    # Report profile when player inactive
    _logger.debug("aioprof enabled. Use caffeinate command on MAC")
    from scheduler import wait_for_player_inactive
    while True:
        t0 = ticks_ms()
        await asyncio.sleep(30)
        await wait_for_player_inactive()
        # Customized version of aioprof.report()
        taskinfo = [(name, count, ms, max) for  name, (count, ms, max, _) in aioprof.timing.items()]

        dt = ticks_diff( ticks_ms(), t0 )
        try:
            total_ms = aioprof.total_time
        except:
            total_ms = sum( x[2] for x in taskinfo )
        # Subtract time used by sleep_us from asyncio times
        # since sleep_us wait time is idle time.
        sleep_us_wait = 0
        #if hasattr( scheduler, "total_sleep_us"):
            # scheduler.total_sleep_us sums all the time
            # waiting with sleep_us for precision.
        #    sleep_us_wait = round(scheduler.total_sleep_us/1000)
        #    scheduler.total_sleep_us = 0
        # Sort by max descending
        taskinfo.sort(key=lambda x:x[3], reverse=True)
        print(f"| name {' '*45} | count  | msec  | max   |")
        for name, count, ms, max in taskinfo:
            if max >= 20 or ms >= 1000:
                #if name == "play_tune":
                #    ms -= sleep_us_wait 
                print(f"| {name:50s} | {count:6d} | {ms:5d} | {max:5d} |")
        # sort by ms descending
        taskinfo.sort( key=lambda x: x[2], reverse=True)
        print(f"| Time since last report {dt=}")
        print(f"| {'Task':30s} | {'msec':5s} | {'%':5s}  |")
        for name, count, msec, max in taskinfo:
            if msec/dt >= 0.001:
                percent = msec/dt*100
                #if name == "play_tune":
                #    name = "play_tune without sleep_us"
                #    percent -= sleep_us_wait/dt*100
                print(f"| {name:30s} | {msec:5d} | {percent:5.0f}% |")
        print(f"| {'total':30s} | {' ':5s} | {(total_ms-sleep_us_wait)/dt*100:5.0f}% |")
        #print(f"| {'sleep_us,not included in total':30s} | {sleep_us_wait:5d} | {sleep_us_wait/dt*100:5.0f}% |")
        taskinfo = None

        aioprof.reset()

# PCA9685, ROMFS, 1 track midi "Tico Tico l rvb 1 MT101 D032.mid"
# | name                                               | count | msec  | max   |
# | midifile_cache_process                             |   110 |  1471 |   742 |
# | play_tune                                          | 71656 | 19519 |   298 |
# | _setlist_process                                   |     5 |   262 |   262 |
# | serve                                              |  1154 |  7564 |    43 |
# | background_garbage_collector                       |    89 |   504 |    39 |
# | _battery_process                                   |     2 |    23 |    22 |
# | Time since last report dt=116279
# | Task                           | msec  | %      |
# | play_tune                      | 19519 |    17% |
# | serve                          |  7564 |     7% |
# | midifile_cache_process         |  1471 |     1% |
# | background_garbage_collector   |   504 |     0% |
# | _setlist_process               |   262 |     0% |
# | _tp_process                    |   197 |     0% |
# | total                          |       |    26% |

# Feb 2026. Comparable player.play_tune() statistics:
# midi_events=5010, msec/event=1.2, busy=5.7%, avg gc=40 msec, late ratio=4.12%


def start_mcserver():
    # Start communication task with server on internet
    # but only if installed.
    try:
        import mcserver # type:ignore
    except ImportError:
        # No impact if mcserver not present.
        # No communication is initiated by this software.
        pass
    except Exception as e:
        print("Exception importing mcserver", e)



async def signal_ready( controller ):
    # Asyncio has started!
    # Show some startup statistics
    t1 = ticks_ms()
    gc.collect()
    gc_t = ticks_diff( ticks_ms(), t1 )
    start_dt = ticks_diff(t1, startup_time)
    alloc = gc.mem_alloc()
    # This allow to check startup time and memory allocation.
    # gc time also can be seen on diag.html
    print(f"Total startup time (without main, until asyncio ready) {start_dt} msec")
    print(f"Memory used at startup {alloc} gc={gc_t} msec")
    # March 2026:
    #   Total startup time (without main, until asyncio ready) 4085 msec
    #   Memory used at startup 137840 gc=28 mse
    # March 2026, freshly installed, no midi files, 20 note pinout.
    #   Total startup time (without main, until asyncio ready) 994 msec
    # Memory used at startup 131872 gc=19 msec

    controller.all_notes_off()
    
    # Tell user system ready by moving some actuators
    await controller.clap(5)
    _led.off()


async def start():
    # Start the software, called with asyncio.run by main.py
    global _led, _logger

    # Ensure /data and /tunelib folders are there
    drehorgel.init_fileops()

    #  Establish global exception handler for asyncio
    asyncio.get_event_loop().set_exception_handler(_handle_exception)

    # Change led color
    drehorgel.init_led()
    _led = drehorgel.led
    _led.starting(0)

    # Get the time/timezone/ntp process going in background.
    # The timezone object is needed for logger, and most modules
    # require logger
    drehorgel.init_timezone()
    getLogger.set_timezone( drehorgel.timezone )
    _logger = getLogger(__name__)
    _led.set_logger( _logger ) # it's only for error count, use startup's logger instance
    
    # Inject getLogger to timezone... it can't import minilog
    # that would be circular imports.
    drehorgel.timezone.setLogger(getLogger)
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

    _led.starting(3)

    await asyncio.gather(
        webserver.run_webserver(),
        scheduler.background_garbage_collector(),
        signal_ready(drehorgel.controller),
        do_aioprof() # only does something if aioprof installed.
    ) # type:ignore

# >>> ideas. 
# >>> Universal board
# >>> Support for MIDI over USB