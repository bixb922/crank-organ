# (c) 2023 Hermann Paul von Borries
# MIT License
# Allows the MIDI player to wait letting well behaved asyncio tasks
# execute during the times between MIDI events.
from micropython import const
import time
import asyncio

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
    # than the for_us wait time between MIDI events.
    #
    # Restriction: this schedules at most one task per wait.
    # but this works well because there are few tasks and many. many MIDI events.
    global _run_always_flag
    t0 = time.ticks_us()
    _run_always_flag = False
    if for_us <= 0:
        return
    if for_us < _RESERVED_US:
        time.sleep_us(for_us)
        return
    _find_and_run_task(for_us - _RESERVED_US)
    await asyncio.sleep_ms(round((for_us - _RESERVED_US)/1000))

    # Wait for the rest of time with more precision
    # This is much more precise (less jitter) than asyncio.sleep_ms()
    # The downside is that during time.sleep_ms() no other tasks can
    # be scheduled, but that is ok, since this is the one and only
    # high priority task.
    remaining_us = for_us - time.ticks_diff(time.ticks_us(), t0)
    if remaining_us > 0:
        time.sleep_us(remaining_us)


def _find_and_run_task(available):
    # only play mode is protected while playing music.
    if _run_always_flag:
        available = _INFINITY
    for i, task in enumerate(_tasklist):
        if task.requested <= available:
            task.available = available  # for debug only
            task.event.set()
            del _tasklist[i]
            return True
    return False


def run_always():
    # At the end of a tune, call run_always() to leave no
    # restrictions for RequestSlice.
    global _run_always_flag
    _run_always_flag = True
    # Schedule all tasks left pending
    # now that the restriction is over.
    while _find_and_run_task(_INFINITY):
        pass


# How to use RequestSlice:
# async with RequestSlice( "descriptive name", requested_msec, [maximum_wait] ):
#       do something
# Will wait for a slice of requested_msec, but task will not be kept waiting
# more than maximum_wait.
# At most one task with "descriptive name" can be pending at the same time.
# This prevents heaping up work that will make system not responsive.
# If maximum_wait is omitted, this is a very low priority
# task that can wait until music has stopped playing.
# Scheduled tasks have to be repetitive and are low priority,
# because if a second task with the same name is scheduled,
# the second task is dismissed. Only one task per name is queued.
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
        self.start = time.ticks_ms()
        if not _run_always_flag:
            # Queue this task for execution
            _tasklist.append(self)
            # Now it has been queued, wait for a time slice
            # but never wait more than the timeout.
            try:
                await asyncio.wait_for_ms(self.event.wait(), self.wait_at_most)
            except asyncio.TimeoutError:
                # Timeout is over, remove from tasklist
                try:
                    i = _tasklist.index(self)
                    del _tasklist[i]
                    if _DEBUG_TIMES:
                        tl = [x.name for x in _tasklist]
                        print(
                            f"task TIMEOUT {self.name}  requested={self.requested} timeout={self.wait_at_most} {tl}"
                        )
                except ValueError:
                    pass
                raise RuntimeError("MIDI player did not let this task run")

        self.t0 = time.ticks_ms()  # For debug
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if _DEBUG_TIMES:
            # This debugging options allows to inspect if times of
            # RequestSlice are ample enough.
            now = time.ticks_ms()
            dt = time.ticks_diff(now, self.t0)
            exceeded = "***** exceeded *****" if dt > self.requested else ""
            waited = time.ticks_diff(now, self.start) - dt
            tl = [x.name for x in _tasklist]
            print(
                f"task {self.name} used={dt}, requested={self.requested}, available={self.available} timeout={self.wait_at_most}, waited {waited} {exc_type=} {exceeded} {tl}"
            )
        # Return None to re-raise any exception


async def wait_for_player_inactive():
    while not _run_always_flag:
        await asyncio.sleep_ms(1000)


# Enable playback: player.py/setlist.py play music
# Disable playback: user is tuning or using pinout
# page, don't react to "start music" requests
playback_enabled = True


def set_playback_mode(p):
    global playback_enabled
    playback_enabled = p

def is_playback_mode():
    return playback_enabled

# Add more info to progress.
def complement_progress(progress):
    # play_mode True: playback is enabled, can start midi files
    # play_mode False: running tuner, don't start midi files
    # because they will interfere with the MIDI files 
    progress["play_mode"] = playback_enabled

# Class to measure time of a group of statements, use:
# with MeasureTime("description") as m:
#       statements
#       statements
# Time is available in m.time_msec
class MeasureTime:
    def __init__(self, title ):
        self.title = title
    def __enter__( self ):
        self.t0 = time.ticks_ms()
        return self
    def __exit__( self, exc_type, exc_val, exc_traceback ):
        self.time_msec = time.ticks_diff( time.ticks_ms(), self.t0 )
        print(f"\tMeasureTime {self.title} {self.time_msec} msec" )


_tasklist = []
_run_always_flag = True
