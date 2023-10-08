# (c) 2023 Hermann Paul von Borries
# MIT License
# Blinks RGB (neopixel) LED. ESP32-S3 boards may have one of these.
import uasyncio as asyncio
import neopixel
import machine
import os
import time

import pinout

TIME_ON = const(50) # millisec the led is on when blinking
BLINK_EVERY = 2_000 # millisec to blink
INTENSITY = const(1) # 1=lowest, 255=highest

def _init( ):
    global neopixel_led, color, time_off, background_task, INTENSITY
    if "ESP32S3" not in os.uname().machine:
        neopixel_led = None
        return
    
    p = pinout.neopixel_pin
    if not p:
        print("No blinking neopixel")
        # No LED task is needed
        return
    
    neopixel_led = neopixel.NeoPixel( machine.Pin(p), 1)

    off()
    color = (4,4,4)
    time_off = 0
    background_task = asyncio.create_task( neopixel_led_process() )

async def neopixel_led_process():
    while True:
        neopixel_led[0] = color
        neopixel_led.write()
        await asyncio.sleep_ms( TIME_ON )
        neopixel_led[0] = (0,0,0)
        neopixel_led.write()
        await asyncio.sleep_ms( time_off )

def on( color ):
    blink( None, color )
    
def off():
    on( (0,0,0) )
    
def blink( period, col ):
    global color, time_off
    if not neopixel_led:
        return
    color = col
    if period:
        time_off = max( 0, int(period - TIME_ON) )
    else:
        # period == None means no blinking
        time_off = 0
    neopixel_led[0] = color
    neopixel_led.write()

def starting( phase ):
    # Shades of green
    if 0 <= phase <= 3:
        on( 
            ( (0,0,INTENSITY), 
              (0,INTENSITY,0), 
              (0,INTENSITY,INTENSITY), 
              (INTENSITY//2,INTENSITY,INTENSITY))[phase] )

def operating(): 
    # Blink green
    blink( BLINK_EVERY, (0,INTENSITY,0) )

def problem():
    # Blink red
    blink( BLINK_EVERY, (INTENSITY,0,0) )

def severe():
    # Magenta on, no blink
    if not neopixel_led:
        return
    background_task.cancel()
    neopixel_led[0] = (INTENSITY,0,int(INTENSITY/2))
    neopixel_led.write()


_init()
