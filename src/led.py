# (c) 2023 Hermann Paul von Borries
# MIT License
# Blinks RGB (neopixel) LED. ESP32-S3 boards may have one of these.
#>>> new options:
#>>> battery heartbeat????
#>>> poweroff idle???
#
import asyncio
import neopixel
import machine
import os
import time

from pinout import gpio
from minilog import getLogger

TIME_ON = const(50) # millisec the led is on when blinking
BLINK_EVERY = 2_000 # millisec to blink
INTENSITY = const(4) # 1=lowest, 255=highest

class BlinkingLed:
    def __init__( self, p ):
        if not p:
            print("No blinking neopixel")
            # No LED task is needed
            return

        self.neopixel_led = neopixel.NeoPixel( machine.Pin(p), 1)

        self.off()
        self.color = (4,4,4)
        self.time_off = 0
        self.background_task = asyncio.create_task( self.neopixel_led_process() )
        self.logger = getLogger( __name__ )
        
    async def neopixel_led_process( self ):
        while True:
            self.neopixel_led[0] = self.color
            self.neopixel_led.write()
            await asyncio.sleep_ms( TIME_ON )
            self.neopixel_led[0] = (0,0,0)
            self.neopixel_led.write()
            await asyncio.sleep_ms( self.time_off )

            if self.logger.get_error_count() > 0:
                self.problem()
                
    def on( self, col ):
        self.blink( None, col )

    def off( self ):
        self.on( (0,0,0) )

    def blink( self, period, col ):

        if not self.neopixel_led:
            return
        self.color = col
        if period:
            self.time_off = max( 0, int(period - TIME_ON) )
        else:
            # period == None means no blinking
            self.time_off = 0
        self.neopixel_led[0] = self.color
        self.neopixel_led.write()

    def starting( self, phase ):
        # Shades of green
        if 0 <= phase <= 3:
            self.on( 
                ( (0,0,INTENSITY), 
                  (0,INTENSITY//2,INTENSITY//2), 
                  (0,INTENSITY,INTENSITY//2),
                 (0,INTENSITY,0), )[phase] )

    async def touch_flash( self ):
        self.on( (128,128,128) )
        await asyncio.sleep_ms(30)
        self.off()
        
    async def blink_ready( self, color, times ):
        for _ in range(times):
            self.on ( color )
            await asyncio.sleep_ms( 100 )
            self.off()
            await asyncio.sleep_ms( 100 )

    def connected( self ):
          asyncio.create_task(
              self.blink_ready( (INTENSITY,INTENSITY,INTENSITY), 5) )
            
    def problem( self ):
        # Blink red
        self.blink( BLINK_EVERY, (INTENSITY,0,0) )

    def severe( self ):
        # Magenta on, no blink
        if not self.neopixel_led:
            return
        self.background_task.cancel()
        self.neopixel_led[0] = (INTENSITY,0,int(INTENSITY/2))
        self.neopixel_led.write()


led = BlinkingLed( gpio.neopixel_pin )
