# (c) 2023 Hermann Paul von Borries
# MIT License
# Blinks RGB (neopixel) LED. 
# ESP32-S3 boards may have one of these.
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
VERY_LOW = const(2)
LOW = const(4) # 1=lowest, 255=highest
STRONG = const(128)

class BlinkingLed:
    def __init__( self, p ):
        if not p:
            # No LED task is needed
            return

        self.neopixel_led = neopixel.NeoPixel( machine.Pin(p), 1)

        self.off()
        self.color = (0,0,LOW)
        self.time_off = 0
        self.background_task = asyncio.create_task( self.neopixel_led_process() )
        self.starting(0)
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
        # ignore if no led defined
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
        self.on( 
                ( (0,0,VERY_LOW), 
                  (0,0,LOW), 
                  (0,VERY_LOW,VERY_LOW),
                 (0,LOW,0), )[phase%4] )

    async def touch_flash( self ):
        self.on( (STRONG,STRONG,STRONG) )
        await asyncio.sleep_ms(30)
        self.off()
        
    def touch_start( self ):
        self.on( (LOW,LOW,LOW) )
        
    async def blink_few( self, color, times ):
        for _ in range(times):
            self.on ( color )
            await asyncio.sleep_ms( 100 )
            self.off()
            await asyncio.sleep_ms( 100 )

    def connected( self ):
        # Create a background task to avoid
        # delaying caller
        asyncio.create_task(
              self.blink_few( (LOW,LOW,LOW), 5) )
            
    def heartbeat_on( self ):
        self.on( (0,LOW,0) )
        
    def heartbeat_off( self ):
        self.off( )
        
    def problem( self ):
        # Blink red
        self.blink( BLINK_EVERY, (LOW,0,0) )

    def short_problem( self ):
        # one blink red
        asyncio.create_task( self.blink_few( (STRONG,STRONG,0), 1) )
        
    def severe( self ):
        # Magenta on, no blink
        if not self.neopixel_led:
            return
        self.background_task.cancel()
        self.neopixel_led[0] = (LOW,0,LOW)
        self.neopixel_led.write()


led = BlinkingLed( gpio.neopixel_pin )
