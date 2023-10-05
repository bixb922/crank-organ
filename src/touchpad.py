import array
import machine
import asyncio

import config

MSEC_BETWEEN_SAMPLES = const(200)
MSEC_SETTLE = const(500)

class TouchButton:
    def __init__( self, gpio_pin ):
        # Only release event, no touch eventt
        self.release_event = asyncio.Event()
        self.big_change = int(config.get_int("touchpad_big_change", 10000) )
        
        if gpio_pin:
            self.tp = machine.TouchPad( machine.Pin( gpio_pin ))
            self.task = asyncio.create_task( self.tp_process() )
        # If no gpio_pin, don't assign button, don't create task.
        # Event will never get set.
      
    def set_release_event( self, ev ):
        self.release_event = ev
        
    async def tp_process( self ): 
        tpval_ant = self.tp.read()
        while True:
            await asyncio.sleep_ms( MSEC_BETWEEN_SAMPLES )
            tpval = self.tp.read()
            if tpval - tpval_ant < -self.big_change:
                self.release_event.set()

                # Wait for touchpad value to settle, and read again
                await asyncio.sleep_ms( MSEC_SETTLE )
                tpval = self.tp.read()

            tpval_ant = tpval

