# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
# Superclass for StartSwitch and StartTouch

from micropython import const 
import asyncio

from drehorgel import led
from minilog import getLogger
 
# Polling interval
_MSEC_BETWEEN_SAMPLES = const(100) 
# Time for TouchPad or Button signal to settle i.e. time to ignore bouncing,
# i.e. TouchPad/Button will not sense a second click if time less than MSEC_SETTLE
_MSEC_SETTLE = const(500)

# _TECHNOLOGY_TOUCHPAD = const(1)
_TECHNOLOGY_SWITCH_TO_GND = const(2)
_TECHNOLOGY_MAX = const(2)

class StartBase:
    # Abstract superclass for StartSwitch and StartTouch
    def __init__( self, gpio_pin ):
        logger = getLogger(__name__)
        # The button allows to register a callback for button/touchpad up
        self.up_callbacks = []
        self.read = lambda : 0 # default in case of an exception below
        if gpio_pin:
            # Call init() of subclass to do the specific initialization
            # init() returns the function to read the value of the button.
            try:
                self.read = self.init( gpio_pin ) # type:ignore
                self.task = asyncio.create_task(self._button_process( ) )
                logger.debug(f"Start button type {self.__class__.__name__} on pin {gpio_pin} initialized")
            except Exception as e:
                logger.exc( e, "Could not initialize button/touchpad pin {gpio_pin} type {self.__class__.__name__}" )
                
    def register_up_callback(self, cb):
        # Triggers when lifting hand up leaving touch pad
        # Several callbacks can be registered, they will all be called when the event occurs.
        self.up_callbacks.append(cb)

    async def _button_process(self ):
        # At startup, wait a bit before reacting and for touchpad reading to settle
        await asyncio.sleep_ms(1000)
        last_val = self.read()
        while True:
            await asyncio.sleep_ms( _MSEC_BETWEEN_SAMPLES )  # type:ignore
            val = self.read()
            # See if this is a transition: hand leaving the touchpad
            # or releasing the button
            if self._transition_up(val, last_val): # type:ignore
                led.off()
                for cb in self.up_callbacks:
                    cb()
                await asyncio.sleep_ms(_MSEC_SETTLE)
                
            # Now see if this is hand touching button or
            # button down;
            elif self._transition_down(val, last_val): # type:ignore
                # Provide visual feedback that the button/touchpad is now down
                # or active or touched or whatever, but on.
                led.touch_start()
                # Could have callbacks here for button/touchpad down.
                await asyncio.sleep_ms( _MSEC_SETTLE )
            last_val = val

    # def read() provided by assignment in init() of subclasses
    # self.read() is also used by pinout.py for tests.
    # Abstract methods:
    # def init(self, gpio ):
    #     return self.read
    # def _transition_up(self, val, last_val):
    #     pass
    # def _transition_down(self, val, last_val):
    #    pass
    
def startButtonFactory( gpio_pin, technology ):
    if technology == _TECHNOLOGY_SWITCH_TO_GND:
        from startswitch import StartSwitch as button_class
    else:
        from starttouch import StartTouch as button_class
    # And return a button instance
    return button_class( gpio_pin )

def validate_technology( technology ):
    if technology and (1 <= technology <= _TECHNOLOGY_MAX):
        return
    raise RuntimeError(f"TouchPad type must be 1 to {_TECHNOLOGY_MAX} but is {technology}")