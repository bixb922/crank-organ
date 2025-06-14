# (c) 2023 Hermann Paul von Borries
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
# and then waits time.sleep_us() which does not yield but
# is very precise.  
_RESERVED_US = 20_000

# Very big int, to use if all time is available to request slices
_INFINITY = const(1_000_000_000)


# If no timeout is specified, use a VERY long time
# longer than the longest tune, 3_600_000 = 1 hour
_LONG_TIME = const(3_600_000)

# If True, RequestSlice shows timing information.
_DEBUG_TIMES = const(False)

async def wait_and_yield_ms(for_us):
    # This function is to wait for the next MIDI event with precision,
    # and allowing another task to run if the time it needs is less
    # than the wait time between MIDI events.
    # Tasks are scheduled with the RequestSlice context manager, see below.
    # for_us is the time to wait in microseconds.
    # Restriction: this schedules at most one task per wait.
    # but this works well because there are few tasks and many, many MIDI events.
    global _run_always_flag
    t0 = ticks_us()
    # If player calls wait_and_yield_ms() it means that
    # _run_always_flag must be set to false, i.e. we have to process
    # time slices.
    _run_always_flag = False
    if for_us <= 0:
        # No time to wait, return immediately
        return
    # If time is rather short, wait with precision
    if for_us < _RESERVED_US:
        sleep_us(for_us)
        return
    # Run a task that can run in the available time, minus
    # the reserved time.
    _find_and_run_task(for_us - _RESERVED_US)
    # Wait for the reserved time yielding control. The task that
    # was found and run should finish within this time.
    await asyncio.sleep_ms(round((for_us - _RESERVED_US)/1000))
    # Now the task continued with _find_and_run_task should
    # have finished.

    # Wait for the rest of time with more precision
    # Waiting with sleep_us() is much more precise (less jitter) 
    # than asyncio.sleep_ms()
    # The downside is that during time.sleep_ms() no other tasks can
    # be scheduled, but that is ok, since this is the one and only
    # high priority task. We don't want to schedule other tasks during
    # this short wait.
    remaining_us = for_us - ticks_diff(ticks_us(), t0)
    if remaining_us > 0:
        sleep_us(remaining_us)


def _find_and_run_task(available):
    if _run_always_flag:
        # If run_always is set, all tasks are scheduled
        available = _INFINITY
    # Find a task that can run in the "available" time slice
    for i, task in enumerate(_tasklist):
        if task.requested <= available:
            task.available = available  # for debug only
            task.event.set()
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
# At most one task with "descriptive name" can be pending at the same time.
# This prevents heaping up work that will make system not responsive.
# If maximum_wait is omitted, this is a very low priority
# task that can wait until music has stopped playing.
# Scheduled tasks should to be repetitive and are low priority,
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
            # Now it has been queued, wait for a time slice
            # but never wait more than the timeout.
            try:
                await asyncio.wait_for_ms(self.event.wait(), self.wait_at_most) # type:ignore
            except asyncio.TimeoutError:
                # Timeout is over, remove from tasklist
                try:
                    i = _tasklist.index(self)
                    del _tasklist[i]
                    if _DEBUG_TIMES:
                        tl = [x.name for x in _tasklist]
                        print(
                            f"task TIMEOUT {self.name}  requested={self.requested} timeout={self.wait_at_most} {tl=}"
                        )
                except ValueError:
                    pass
                raise RuntimeError("MIDI player did not let this task run")

        self.t0 = ticks_ms()  # For debug
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if _DEBUG_TIMES:
            # This debugging options allows to inspect if times of
            # RequestSlice are ample enough.
            now = ticks_ms()
            dt = ticks_diff(now, self.t0)
            exceeded = "***** exceeded *****" if dt > self.requested else ""
            waited = ticks_diff(now, self.start) - dt
            tl = [x.name for x in _tasklist]
            print(
                f"task {self.name} used={dt}, requested={self.requested}, available={self.available} timeout={self.wait_at_most}, waited {waited} {exc_type=} {exceeded} {tl=}"
            )
        # Return None to re-raise any exception

async def wait_for_player_inactive():
    # used by mcserver
    while not _run_always_flag:
        await asyncio.sleep_ms(1000)



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
max_gc_time = 0 # Expose maximum garbage collect time for webserver.py /diag.html
async def background_garbage_collector( ):
    global max_gc_time

    # With MicroPython 1.21 and later, gc.collect() is not very critical anymore
    # But I'll still keep the code. Now gc.collect() duration depends on
    # RAM allocated and not total RAM size.

    while True:
        # Run garbage collector every 3 seconds
        # gc is best if not delayed more than a few seconds
        # If time is longer, gc takes longer too.
        await asyncio.sleep_ms(3_000)

        # Measured times, minimum: after startup. Maximum: during playback
        # VCC-GND  gc=49-61
        # Weact gc=28-50
        # No name board gc=48-60

        # gc.collect() times just before starting async loop
        # No name board 48 msec
        # Weact board 43 msec
        # VCC-GND board 48 msec

        try:
            # Request a slice of max_gc_time msec to run 
            # garbage collector
            async with RequestSlice( "gc.collect", max_gc_time, 10_000 ):
                t0 = ticks_ms()
                gc.collect()
                # Adjust gc time upwards if initial estimate too low
                max_gc_time = max( max_gc_time, ticks_diff( ticks_ms(), t0) )

        except RuntimeError:
            # If RequestSlice times out, collect garbage anyhow
            # No good to accumulate pending gc, gc time increases
            # but a MemoryError is not likely, since there
            # should be plenty of RAM with 8Mb
            gc.collect()

# This has to go somewhere. Used by pcnt.py and minilog.py
def singleton(cls):
    instance = None
    def getinstance(*args, **kwargs):
        nonlocal instance
        if instance is None:
            instance = cls(*args, **kwargs)
        return instance
    return getinstance


_tasklist = []
_run_always_flag = True
