
import uasyncio as asyncio
import json
import gc
from array import array
from time import ticks_ms, ticks_diff
from machine import Timer, Pin

from minilog import getLogger
import config
from pinout import tachometer_pin

# Number of stripes on wheel
STRIPES = const(16) 
# How often to recalculate RPS
CALCULATE_EVERY_MS = const(300)
COUNTER_HISTORY_STORED = const(4)
# Less than 0.3 RPS is stopped
_MINIMUM_RPSEC = 0.3 
# "Normal" speed, when MIDI speed = real speed
_NORMAL_RPSEC = 1.2

# To filter bad IRQ
MINIMUM_MSEC_BETWEEN_IRQ = int(1000/_NORMAL_RPSEC/STRIPES/4)


# IRQ array has 3 elements: rising edge count,
# falling edge count and element to test
RISING_COUNT = const(1)
FALLING_COUNT = const(0)
TEST_TOGGLE = const(2) # _timer_irq uses this, for test only
irq_array = array("i", (0, 0, 0 ) )

def _pin_irq( p ):
    global irq_array
    # If p.value()==0 count falling edge
    # If p.value()==1 count rising edge
    irq_array[p.value()] += 1
    

# Simulate rising/falling edge
def _timer_irq(t):
    if irq_array[TEST_TOGGLE] == 0:
        irq_array[0] += 1
        irq_array[TEST_TOGGLE] = 1
    else:
        irq_array[1] += 1
        irq_array[TEST_TOGGLE] = 0
    
    # RPSEC is the actual revolutions per second measured
    # When in test mode, this is emulated with timer
    # Velocity is a superimposed manual control to alter the "normal"
    # playback speed. _ui_velocity is the velocity as set by the ui
    # (50=normal, 0=lowest, 100=highest). 

# Last calculated RPS value
rpsec = 0

def _init():
    global _logger, rpsec, _calculate_task

    _logger = getLogger( __name__ )
    
    # Set UI reference to 50, halfway from 0 to 100.
    set_velocity( 50 )
    
    _calculate_task = asyncio.create_task( _calculate_rpsec() )
    _logger.debug( "init ok" )
        
async def _calculate_rpsec():
    global irq_array, rpsec
    
    if not tachometer_pin:
        rpsec = _NORMAL_RPSEC
        return
    
    tachometer_device = Pin( tachometer_pin, Pin.IN )
    tachometer_device.irq( trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=_pin_irq)  
    
    prev_t = ticks_ms()
    history = []
    while True:
        await asyncio.sleep_ms( CALCULATE_EVERY_MS )
        if mode == MODE_PAUSED:
            rpsec = 0
            continue
        t = ticks_ms()
        dt = ticks_diff( t, prev_t )/1000
        # >>> DESIGN LOGIC TO SUPRESS FLUTTER AND OTHER ERRORS
        # irq_array[rising] and [falling] must be similar
        # If not, may be better to keep previous value
        if abs(irq_array[RISING_COUNT] - irq_array[FALLING_COUNT]) < 4:
            history.append( (irq_array[RISING_COUNT] + irq_array[RISING_COUNT])/STRIPES / dt / 2 )
        # Reinitialize counters
        irq_array[FALLING_COUNT] = 0
        irq_array[RISING_COUNT] = 0
        while len(history) > COUNTER_HISTORY_STORED:
            history.pop(0)
        rpsec = sum( history )/len( history )
        prev_t = t
        
def get_rpsec():
    global rpsec
    return rpsec

def is_turning():
    global rpsec
    return rpsec > _MINIMUM_RPSEC

def is_really_turning():
    return tachometer_pin and is_turning()

def clear():
    pass

def get_normalized_rpsec():
    global rpsec, _velocity_multiplier
    return rpsec * _velocity_multiplier
    
def set_velocity( ui_vel ):
    global _velocity_multiplier, _ui_velocity
    _ui_velocity = ui_vel
    # The UI sets _ui_velocity to a value from 0 and 100, normal=50.
    # _ui_velocity is a multiplier, 1=normal, 2=double speed, 0.5=half speed
    # f(0) => 0.5
    # f(50) => 1
    # f(100) => 2
    # Calculate the multiplier needed by get_normalized_rpsec
    _velocity_multiplier = (ui_vel*ui_vel/10000 + ui_vel/200 + 0.5)/_NORMAL_RPSEC

def get_velocity():
    return _ui_velocity


_init()   
