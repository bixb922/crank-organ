# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# Allows the MIDI player to wait letting well behaved asyncio tasks
# execute during the times between MIDI events.
from micropython import const
from time import ticks_diff, ticks_us, ticks_ms, sleep_us
import asyncio
import gc

_run_always_flag = True

# Time that is spent waiting with precision timer.
# On ESP32 and ESP32-S3, async.sleep_ms() is done
# in clock ticks of 10 or 20 ms, so it's not precise at
# all. Leaving a RESERVED_US waits short of this time
# and then time.sleep_us() is used. 
# sleep_us() does not yield but is very precise,
# correcting the error of async.sleep_ms most of the times.
_RESERVED_USEC = const(15_000) # last value 15_000
# With this value, remaining_us is in the average around 10 msec
# and is rarely negative. The cause of this is that asyncio.sleep_ms()
# takes, on the average, 5 msec more than specified.

# Very big int, to use if all time is available to request slices, 
# (but still a MicroPython small int)
_INFINITY = const(199_999_999)


# If no timeout is specified, use a VERY long time
# longer than the longest tune, 3_600_000 msec = 1 hour
_LONG_TIME = const(3_600_000)

# If True, RequestSlice shows timing information.
_DEBUG_TIMES = const(False)

# Reading the response lines after the first line in Microdot
# takes 150 to 300 msec in async but blocks sometimes for 50 msec
# making this wait here late by around 50msec.
# I patched Microdot with a small asyn delay for safe_read_line()
# for the subsequent readlines. The initial readline() for the request line
# does not cause problems. 

# Tally CPU used in time.sleep_us() for aioprof statistics

async def wait_and_yield_usec(for_usec):
    # This function allows to wait for the next MIDI event with precision,
    # and allowing another task to run if the time it needs is less
    # than the wait time between MIDI events.
    # Tasks are scheduled with the RequestSlice context manager, see below.
    # for_usec is the time to wait in microseconds.
    # This schedules at most one task per wait.
    # but this works well since there are few tasks and many MIDI events.
    global _run_always_flag
    # If player calls wait_and_yield_usec() it means that
    # _run_always_flag must be set to false, 
    # no free RequestSlice anymore
    _run_always_flag = False
    
    t_start = ticks_us()
    async_time = round((for_usec - _RESERVED_USEC)/1000)
    
    if async_time > 0:
        # Run one task that can run in the available time, minus
        # the reserved time.
        _find_and_run_task( async_time )

    # Wait until the time expires, yielding control.
    while ticks_diff( ticks_us(), t_start ) < for_usec:
        await asyncio.sleep_ms(0) # better precision when using 0 msec

def _find_and_run_task(async_time):
    available = async_time # in msec
    if _run_always_flag:
        # If run_always is set, all tasks are scheduled
        available = _INFINITY
    # Find a requested slice that can run in the "available" time slice
    for i, requested_slice in enumerate(_tasklist):
        if requested_slice.requested <= available:
            requested_slice.available = available  # for debug only
            requested_slice.event.set() # kick the task to continue
            del _tasklist[i]
            return True
    return False


def run_always():
    # At the end of a tune, call run_always() to leave no
    # restrictions for RequestSlice. I.e. when no tune is playing,
    # RequestSlice runs the enclosed code with no delay.
    global _run_always_flag
    _run_always_flag = True
    # Schedule all tasks left pending
    # now that the restriction is over.
    while _find_and_run_task(_INFINITY):
        pass


# How to use RequestSlice:
# async with RequestSlice( "descriptive name", requested_msec, [maximum_wait] ):
#       do something
# Will wait for a slice of requested_msec, but caller will not be kept waiting
# more than maximum_wait.
# The priority task (i.e playing MIDI files) must use wait_and_yield_usec() to yield to
# the scheduler and make RequestSlice() do its magic.
# If the priority task calls run_always(), then RequestSlice() will 
# not block, and RequestSlice() tasks will run freely.
# At most one task with "descriptive name" can be pending at the same time.
# This prevents heaping up work that will make system not responsive.
# If maximum_wait is omitted, this is a very low priority
# task that can wait until music has stopped playing.
# Scheduled tasks should to be repetitive and are designed low priority,
# because if a second task with the same name is scheduled,
# the first task is dismissed. Only one task per name is queued.
# For example: recalculate battery level once a minute, if that 
# task is delayed, no serious problem will occur.
class RequestSlice:
    # Default timeout: much longer than one tune = 1 hour.
    # This means: wait until the current tune is
    # over, this is low priority.
    def __init__(self, name, requested, wait_at_most=_LONG_TIME):
        self.name = name
        self.requested = requested
        self.event = asyncio.Event()
        self.available = _INFINITY
        self.wait_at_most = wait_at_most
        return

    async def __aenter__(self):
        self.start = ticks_ms()
        if not _run_always_flag:
            # Queue this task for execution
            _tasklist.append(self)
            # Now it has been queued, wait for a time slice to become available
            # but never wait more than the timeout.
            try:
                await asyncio.wait_for_ms(self.event.wait(), self.wait_at_most) # type:ignore
            except asyncio.TimeoutError:
                # self.wait_at_most is over, remove from tasklist
                try:
                    i = _tasklist.index(self)
                    del _tasklist[i]
                    if _DEBUG_TIMES:
                        # tl = [x.name for x in _tasklist]
                        print(
                            f"task TIMEOUT {self.name}  requested={self.requested}"
                        )
                except ValueError:
                    pass
                # Note that at this point, run_always_flag may be true, so the
                # exception is undeserved... but nothing bad will happen.
                raise RuntimeError("MIDI player did not let this task run")

        self.t0 = ticks_ms()  # For debug
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if _DEBUG_TIMES:
            # This debugging options allows to inspect if times of
            # RequestSlice are ample enough.
            now = ticks_ms()
            dt = ticks_diff(now, self.t0)
            exceeded = "***** exceeded requested *****" if dt > self.requested else ""
            waited = ticks_diff(now, self.start) - dt
            #tl = [f"{x.name} requested={x.requested} waiting={ticks_diff(now, self.start)}" for x in _tasklist]
            print(
                f"task {self.name} used={dt}, requested={self.requested}, available={self.available} timeout={self.wait_at_most}, waited {waited} {exc_type=} {exceeded}"
            )
        elif not _run_always_flag:
            # Check this only when a tune is playing
            dt = ticks_diff(ticks_ms(),self.t0 )
            if dt > self.requested:
                print(f"RequestSlice {self.name} requested time exceeded used={dt} requested={self.requested} msec")
        # Return None to re-raise any exception

async def wait_for_player_inactive():
    while not _run_always_flag:
        await asyncio.sleep_ms(1000)

def is_player_active():
    return not _run_always_flag


# Class to measure time of a group of statements, use:
# with MeasureTime("description") as m:
#       statements
#       statements
# Time is available in m.time_msec
class MeasureTime:
    def __init__(self, title ):
        self.title = title
    def __enter__( self ):
        self.t0 = ticks_ms()
        return self
    def __exit__( self, exc_type, exc_val, exc_traceback ):
        self.time_msec = ticks_diff( ticks_ms(), self.t0 )
        print(f"\tMeasureTime {self.title} {self.time_msec} msec" )

# This measurement is slow!
class MeasureMemory:
    def __init__(self, title ):
        self.title = title
    def __enter__( self ):
        gc.collect()
        self.m0 = gc.mem_alloc()
        return self
    def __exit__( self, exc_type, exc_val, exc_traceback ):
        gc.collect()
        gc.collect()
        self.alloc = gc.mem_alloc() - self.m0 
        print(f"\tMeasureMemory {self.title} {self.alloc} bytes" )
 
# This garbage collector does not interfere with music playback:
# it works in the wait times between notes.
max_gc_time = 0 # Expose maximum garbage collect time for webserver.py /diag.html (while player is playing)
avg_gc_time = 0 # and running average, needed to fit this in available slices.
def collect_garbage(reset=False, report=False):

    # Do a gc.collect() and feed indicators
    global max_gc_time, avg_gc_time
    t0 = ticks_ms()
    gc.collect()
    t =  ticks_diff( ticks_ms(), t0 ) 
    if is_player_active():
        max_gc_time = max( max_gc_time, t ) # for statistics on diag page only
    if report:
        print(f"GC timeout garbage collection took {t} msec, max {max_gc_time} msec, average {avg_gc_time} msec, {is_player_active()=}") 

# >>> check gc timeout
# 2026-04-09 12:34:05GMT-4 - player - INFO - Actuator stats: max polyphony=12
# 2026-04-09 12:34:06GMT-4 - history - DEBUG - 802 elements in history
# 2026-04-09 12:34:23GMT-4 - player - INFO - Start tuneid=ik6rF-7NL '~LM068 A029 O du lieber Augustin rvb 1' tracks=5
# GC timeout garbage collection took 32 msec, max 35 msec, average 32 msec, is_player_active()=True
# GC timeout garbage collection took 33 msec, max 35 msec, average 32 msec, is_player_active()=True
# GC timeout garbage collection took 33 msec, max 35 msec, average 32 msec, is_player_active()=True
# 2026-04-09 12:35:35GMT-4 - player - INFO - MIDI processing: midi_events=1252, msec/event=1.1, busy=1.9%, avg gc=32 msec, late ratio=0.18%
# 2026-04-09 12:35:36GMT-4 - player - INFO - End tuneid=ik6rF-7NL '~LM068 A029 O du lieber Augustin rvb 1' midi_fn=tunelib/LM068_A029 O du lieber Augustin rvb 1.mid, played 72.04s of 72.04s
# 2026-04-09 12:35:36GMT-4 - player - INFO - Actuator stats: max polyphony=8
# 2026-04-09 12:35:36GMT-4 - history - DEBUG - 803 elements in history
# GC timeout garbage collection took 31 msec, max 35 msec, average 32 msec, is_player_active()=False
# 2026-04-09 12:35:53GMT-4 - player - INFO - Start tuneid=ieLbmwEM5 '~marche des patineurs  yvette horner r1' tracks=15
# 2026-04-09 12:38:48GMT-4 - player - INFO - MIDI processing: midi_events=12432, msec/event=1.1, busy=8.0%, avg gc=34 msec, late ratio=0.38%
# 2026-04-09 12:38:48GMT-4 - player - INFO - End tuneid=ieLbmwEM5 '~marche des patineurs  yvette horner r1' midi_fn=tunelib/marche des patineurs - yvette horner r1.mid, played 173.94s of 173.94s

    if reset:
        avg_gc_time = t*2 # gc time just before playing, reset history
    else:
        avg_gc_time = round((avg_gc_time+t)/2)
        
async def background_garbage_collector( ):
    # gc should not interfere with player
    # Disable gc and manage manually.
    # gc.threshold() is -1 by default
    gc.disable()
    # With MicroPython 1.21 and later, gc.collect() is not very critical anymore
    # With plain flash files (no ROMFS) and 1500 MIDI files, gc times can go up to nearly 500 ms
    # but mainly during startup. During playback, gc times are around 30- 70 msec.
    # Finding 100 ms of pause in a MIDI file is not difficult, so 
    # the impact of garbace collection is minimal.
    while True:
        # Run garbage collector every second
        # gc is best if not delayed more than a few seconds
        # If time is longer, gc takes longer too.
        await asyncio.sleep_ms(1_000)
        try:
            # Request a slice of enough time to run 
            # garbage collector
            async with RequestSlice( "gc.collect", max(40,round(avg_gc_time+15)), 10_000 ):
                collect_garbage()

        except RuntimeError:
            # If RequestSlice times out, collect garbage anyhow
            # No good to accumulate pending gc, gc time increases
            # but a MemoryError is not likely, since there
            # should be plenty of RAM with 8Mb
            collect_garbage(report=True)

# This has to go somewhere. Used by pcnt.py and minilog.py
# can be dropped when internal pcnt is dropped.
#def singleton(cls):
#    instance = None
#    def getinstance(*args, **kwargs):
#        nonlocal instance
#        if instance is None:
#            instance = cls(*args, **kwargs)
#    return getinstance
#        return instance


_tasklist = []
_run_always_flag = True


# Fast logger for debug of time critical code while playing MIDI
# fdata = []
# flogt0 = ticks_ms()
# def flinit():
#     global fdata, flogt0
#     fdata = []
#     flogt0 = ticks_ms()
# def flog(s):
#     fdata.append(f"{ticks_diff(ticks_ms(),flogt0):6d} {s}")
# def fdump():
#     if fdata:
#         print(">>>fdump start")
#         for s in fdata:
#             print(s)
#         print(">>>fdump end")
#     flinit()
# flinit()

# debugt0 = ticks_ms()
# def debugtime(s):
#      global debugt0
#      t1 = ticks_ms()
#      print(f">>>DEBUGTIME {s} {ticks_diff(t1,debugt0)} msec")
#      debugt0 = t1
