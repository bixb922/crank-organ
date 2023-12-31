# (c) 2023 Hermann Paul von Borries
# MIT License
# Crank rotation speed sensor. Still in testing phase.
# >>> REFACTOR
import asyncio
from array import array
from time import ticks_ms, ticks_diff
from machine import Pin

from minilog import getLogger
from pinout import gpio

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
MINIMUM_MSEC_BETWEEN_IRQ = int(1000 / _NORMAL_RPSEC / STRIPES / 4)


# IRQ array has 3 elements: rising edge count,
# falling edge count and element to test
RISING_COUNT = const(1)
FALLING_COUNT = const(0)
TEST_TOGGLE = const(2)  # _timer_irq uses this, for test only
irq_array = array("i", (0, 0, 0))


def _pin_irq(p):
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

    # Velocity is a superimposed manual control to alter the "normal"
    # playback speed. _ui_velocity is the velocity as set by the ui
    # (50=normal, 0=lowest, 100=highest).


# Last calculated RPS value
rpsec = 0


def _init():
    global _logger, rpsec, _calculate_task, _start_turning_event

    _logger = getLogger(__name__)

    # Set UI reference to 50, halfway from 0 to 100.
    set_velocity(50)
    _start_turning_event = asyncio.Event()
    _calculate_task = asyncio.create_task(_calculate_rpsec())

    _logger.debug("init ok")


def set_start_turning_event(ev):
    global _start_turning_event
    _start_turning_event = ev


async def _calculate_rpsec():
    global irq_array, rpsec, tachometer_pin

    tachometer_pin = gpio.tachometer_pin
    if not tachometer_pin:
        rpsec = _NORMAL_RPSEC
        return

    tachometer_device = Pin(tachometer_pin, Pin.IN)
    tachometer_device.irq(
        trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=_pin_irq
    )

    prev_t = ticks_ms()
    history = []
    last_rpsec = 0
    while True:
        await asyncio.sleep_ms(CALCULATE_EVERY_MS)
        t = ticks_ms()
        dt = ticks_diff(t, prev_t) / 1000
        # >>> DESIGN LOGIC TO SUPRESS FLUTTER AND OTHER ERRORS
        # irq_array[rising] and [falling] must be similar
        # If not, may be better to keep previous value
        if abs(irq_array[RISING_COUNT] - irq_array[FALLING_COUNT]) < 4:
            history.append(
                (irq_array[RISING_COUNT] + irq_array[RISING_COUNT])
                / STRIPES
                / dt
                / 2
            )
        # Reinitialize counters
        irq_array[FALLING_COUNT] = 0
        irq_array[RISING_COUNT] = 0
        while len(history) > COUNTER_HISTORY_STORED:
            history.pop(0)
        rpsec = sum(history) / len(history)

        if last_rpsec < _MINIMUM_RPSEC and rpsec > _MINIMUM_RPSEC:
            _start_turning_event.set()

        prev_t = t


def is_turning():
    global rpsec
    return is_installed() and rpsec > _MINIMUM_RPSEC


def is_installed():
    return bool(tachometer_pin)


def clear():
    # Clear "turning start" event - we don't need that here...
    pass


def get_normalized_rpsec():
    global rpsec, _velocity_multiplier
    # Used in player.py to delay/hasten music
    # depending on crank speed
    return rpsec * _velocity_multiplier


def set_velocity(ui_vel):
    global _velocity_multiplier, _ui_velocity
    _ui_velocity = ui_vel
    # The UI sets _ui_velocity to a value from 0 and 100, normal=50.
    # _ui_velocity is a multiplier, 1=normal, 2=double speed, 0.5=half speed
    # f(0) => 0.5
    # f(50) => 1
    # f(100) => 2
    # Calculate the multiplier needed by get_normalized_rpsec
    _velocity_multiplier = (
        ui_vel * ui_vel / 10000 + ui_vel / 200 + 0.5
    ) / _NORMAL_RPSEC


def complement_progress(progress):
    global _ui_velocity, rpsec
    progress["velocity"] = _ui_velocity
    progress["rpsec"] = rpsec
    progress["is_turning"] = is_turning()


_init()
