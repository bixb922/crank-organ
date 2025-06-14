from driver_gpio import BaseDriver, BasePin
from machine import PWM, Pin
# This class is instantiated when a ["gpioservo", x,x,x] entry
# is found in pinout.json.
# The driver can handle up to 8 PWM channels for RC servos (radio control servos)
# These servos need a pulse at least every 20 msec
# Pulse with 1 msec = 0 degree turn, pulse with 2msec = 180 degree turn.

class GPIOServoDriver(BaseDriver):
    def __init__( self, period_us, pulse0_us, pulse1_us ):
        # Check again. Bad things happen if not in range
        if not( 1000 <= pulse0_us <= 2000 ) or not( 1000 <= pulse1_us <= 2000):
            raise RuntimeError("Pulse width must be between 1000 and 2000")
        # Need a list of all pins for .all_notes_off() function
        self._pwm_pins = [] 
        self.repr = f"GPIOServo({period_us},{pulse0_us},{pulse1_us})"

        self._frequency = round(1_000_000/period_us)
        self._duty0 = round(pulse0_us/period_us*65536)
        self._duty1 = round(pulse1_us/period_us*65536)

    def define_pin( self, *args ):
        # Return a individual pin
        sp = GPIOServoPin( self, self._frequency, self._duty0, self._duty1, *args )
        # Same pin could be twice in pwm_pins because of register definitions
        self._pwm_pins.append( sp )
        return sp

    def all_notes_off( self ):
        for sp in self._pwm_pins:
            sp.value(0)

    def __repr__( self ):
        # This repr is also used in solenoid.py, web test pin
        # See __init__ for format.
        return self.repr
    

class GPIOServoPin(BasePin):
    def __init__( self, driver, frequency, duty0, duty1, pin_number, rank, nominal_midi_note ):
        self._duty0 = duty0
        self._duty1 = duty1
        self._pwm = PWM( Pin(pin_number), 
                            freq=frequency,
                            duty_u16=duty0 )
        super().__init__(driver, pin_number, rank, nominal_midi_note )

    def value( self, val ):
        self._pwm.duty_u16( self._duty1 if val else self._duty0 )
