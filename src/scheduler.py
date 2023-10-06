# Allows the MIDI player to wait letting well behaved asyncio tasks
# execute during the times between MIDI events.

import time
import asyncio

_may_run = asyncio.Event()
_run_always_flag = True

_RESERVED_MS = 20
_MAXIMUM_TASK_TIME = 520 - _RESERVED_MS
_INFINITY = const(999_999_999)
_DEBUG_TIMES = False # If True, RequestSlice shows timing information.

async def wait_and_yield_ms( for_ms ):
    # This function is to wait for the next MIDI event with precision,
    # and allowing another task to run if the time it needs is less
    # than the for_ms wait time between MIDI events.
    #
    # Restriction: this schedules at most one task per wait.
    # but this works well because there are few tasks and many. many events.
    global _run_always_flag
    t0 = time.ticks_us()
    _run_always_flag = False
    if for_ms <= 0:
        return    
    if for_ms < _RESERVED_MS:
        time.sleep_us( for_ms*1000 )
        return
    _find_and_run_task( for_ms - _RESERVED_MS )
    await asyncio.sleep_ms( for_ms - _RESERVED_MS )    

    # Wait for the rest of time with more precision
    # This is much more precise (less jitter) than asyncio.sleep_ms()
    # The downside is that during time.sleep_ms() no other tasks can
    # be scheduled, but that is ok, since this is the one and #
    # high priority task.
    duration_us = time.ticks_diff( time.ticks_us(), t0 )
    remaining_us = for_ms * 1_000 - duration_us
    if remaining_us > 0:
        time.sleep_us( remaining_us )
    
def _find_and_run_task( available ):
    # only play mode is protected while playing music.
    if _run_always_flag:
        available = _INFINITY
    for name, task in _tasklist.items():
        if task.requested <= available:
            task.available = available
            task.event.set()
            del _tasklist[name]
            return True
    return False

def run_always():
    # At the end of a tune, call run_always() to leave no
    # restrictions for RequestSlice.
    global _run_always_flag
    _run_always_flag = True
    # Run pending tasks now.
    while _find_and_run_task( _INFINITY ):
        pass
        
# Use:
# with RequestSlice( "descriptive name", requested_msec, maximum_wait ):
#       do something
# Will wait for a slice of requested_msec, but will not be kept waiting
# more than maximum_wait.
# At most one task with "descriptive name" can be pending at the same time.
# This prevents heaping up work that will make system not responsive.
# Scheduled tasks have to be repetitive and low priority.
class RequestSlice:
    def __init__( self, name, requested, timeout ):
        self.name = name
        self.requested = requested
        self.event = asyncio.Event()
        self.available = _INFINITY
        self.timeout = timeout
        self.timeout_seen = False
        return

    async def __aenter__( self ):
        if not _run_always_flag:
            # Queue this task for execution
            if self.name not in _tasklist:
                # Each task (by name) only once
                _tasklist[self.name] = self
                try:
                    # Now it has been queued, wait for a time slice
                    # but never wait more than the timeout.
                    await asyncio.wait_for( self.event.wait(), self.timeout )
                except asyncio.TimeoutError:
                    self.timeout_seen = True
                    pass
        self.t0 = time.ticks_ms()
        return self
        
    async def __aexit__( self, exc_type, exc_value, traceback ):
        if _DEBUG_TIMES:
            # This debugging options allows to inspectss if parameteres of
            # RequestSlice are correct.
            dt = time.ticks_diff( time.ticks_ms(), self.t0 )
            exceeded = "***** exceeded " if dt > self.requested else ""
            timeout = "***** timeout " if self.timeout_seen else ""
            print(f"task {self.name} used={dt}, requested={self.requested}, available={self.available} timeout={self.timeout} {exceeded} {timeout}")
        return self

           
def _init():
    global _tasklist
    _tasklist = {}
    _run_always_flag = True

_init()
  
