# (c) 2023 Hermann Paul von Borries
# MIT License
# Touchpad asyncio driver, detects button down event in background
# and triggers events defined by registering.
from micropython import const 
import machine 
import asyncio
from time import ticks_ms, ticks_diff, ticks_add

from drehorgel import config, led

 
# Polling interval
MSEC_BETWEEN_SAMPLES = const(100) 
# Time for TouchPad signal to settle == time to ignore bouncing,
# TouchPad will not sense a second click if time less than MSEC_SETTLE
MSEC_SETTLE = const(100)
# If two touches occur within this interval, it's a "double touch"
DOUBLE_TOUCH_MAX = const(1000)
DOUBLE_TOUCH_MIN = const(300)

class TouchButton:
    def __init__(self, gpio_pin):
        # The TouchButton allows to register an
        #  asyncio.Events() for each action (up, down, double down)
        # Assign a dummy event initially, to be replaced by the caller.

        # Hand goes up from touchpad:
        self.up_event = asyncio.Event()

        # Hand goes down on touchpad (not used for now)
        self.down_event =  self.up_event

        # Two down events in succesion (like a "double click"):
        self.double_event = self.up_event
        
        
        if gpio_pin:
            self.task = asyncio.create_task(self._tp_process(  machine.TouchPad(machine.Pin(gpio_pin) )))
        # If no gpio_pin, don't assign pin, don't create task.
        # Events will never get set.

    def register_up_event(self, ev):
        # Event when lifting hand up leaving touch pad
        self.up_event = ev
    
    # Not needed
    #def register_down_event(self,ev):
    #    # Not used by now
    #    # Event when putting hand down on touch pad
    #    self.down_event = ev

    # Not needed
    # def register_double_event(self,ev):
    #     # Event when twice down in a row (similar to double-click on PC but slower)
    #     self.double_event = ev

 
    async def _tp_process(self, tp ):
        # At startup, wait a bit before reacting and for touchpad reading to settle
        await asyncio.sleep(1)
        # Last_up and previous_up are times of previous touches
        # Initialize last_up and previous up in the very past
                # Sensitivity of touchpad: size of change to cause an event
        big_change = config.get_int("touchpad_big_change") or 10000

        previous_up = ticks_add(ticks_ms(),-DOUBLE_TOUCH_MAX) 
        last_up = previous_up
        tpval_ant = tp.read()
        # >>> could optimize, double and up events
        # >>> currently not needed
        while True:
            await asyncio.sleep_ms( MSEC_BETWEEN_SAMPLES )  # type:ignore
            tpval = tp.read()
            # See if this is a transition: hand leaving the touchpad
            if tpval-tpval_ant<(-big_change):
                led.off()
                # Touch end: set event to publish this
                self.up_event.set()
                # Keep time of last 2 touch events
                previous_up = last_up
                last_up = ticks_ms()  # type:ignore
                # >>> double touch not needed
                # See if this is a "double touch"
                dt = ticks_diff(last_up,previous_up)
                if DOUBLE_TOUCH_MIN<=dt<=DOUBLE_TOUCH_MAX:
                    self.double_event.set()
                    # 3 touch down in a row will yield 2 double events...
                # Wait for touchpad value to settle, and read again
                await asyncio.sleep_ms(MSEC_SETTLE)
            # See if this is a transition: hand touching the touchpad
            elif tpval-tpval_ant>big_change:
                # Touch down: show led, activate event, wait for signal to settle
                led.touch_start()
                self.down_event.set()
                await asyncio.sleep_ms( MSEC_SETTLE )  

                
            tpval_ant = tpval

