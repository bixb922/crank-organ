import asyncio
from machine import Pin, Encoder # type:ignore

from minilog import getLogger
# Rotary encoder to set tempo
# This is a potentiometer type rotary encoder,
# not the crank revolution sensor.
# The effect of this sensor is added to the crank sensor and UI setting
# Keep if needed in the future

# >>> add test button?
class TempoEncoder:

    def __init__( self, crank, tempo_a, tempo_b, tempo_switch, rotary_tempo_mult ):
        self.logger = getLogger(__name__)
        # Both A and B input must be present for the
        # rotary encoder to work. Switch is optional.
        encoder = Encoder( 1, filter_ns=13000, # Highest value possible
                            phase_a=Pin( tempo_a, Pin.IN, Pin.PULL_UP ), 
                            phase_b=Pin( tempo_b, Pin.IN, Pin.PULL_UP ), 
                            phases=1)
        self.tempo_task = asyncio.create_task( self._tempo_process( encoder, rotary_tempo_mult, crank ) )

        # Switch is optional
        if tempo_switch:
            switch = Pin( tempo_switch, Pin.IN, Pin.PULL_UP )
            self.switch_task = asyncio.create_task( self._switch_process( switch, crank ))
        self.logger.debug("init ok")


    async def _tempo_process(self, encoder, rotary_tempo_mult, crank ):
        encoder.value(0)
        while True:
            # Read velocity several times a second 
            await asyncio.sleep_ms(200)
            # Read pulses since last read, reset counter to 0.
            if (v := encoder.value(0)):
                crank.set_velocity_relative( v * rotary_tempo_mult )  
        
    async def _switch_process( self, switch, crank ):
        # This detects a long press of the rotary encoder's switch
        # considering that the switch is very, very noisy and bouncy.
        while True:
            await asyncio.sleep_ms(300)
            # Wait until switch pressed (.value()==0 is "pressed")
            if switch.value() == 0:
                # Switch is now "on", see if it stays 
                # steadily on
                # for about 0.8 seconds. 
                # I have a rather
                # low quality rotary encoder where the
                # switch toggles when the rotary encoder counts.
                # Or perhaps I don't know how to use that thing.
                v = 0
                for _ in range(40):
                    # Sample frequently
                    await asyncio.sleep_ms(20)
                    if(v := switch.value()): 
                        break
                # Was switch never off during this time?
                if v == 0:
                    crank.set_velocity(50)
