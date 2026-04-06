from machine import PWM, Pin
from driver_base import RCServoPin, BaseDriver

# This class is instantiated when a ["gpioservo", x,x,x] entry
# is found in pinout.json.
# The driver can handle up to 8 PWM channels for RC servos (radio control servos)
# These servos need a pulse at least every 20 msec
# Pulse with 1 msec = 0 degree turn, pulse with 2msec = 180 degree turn.

class GPIOServoDriver(BaseDriver):

    def __init__( self, period_us ):
        super().__init__( )
        self._period_us = period_us # Needed to calculate duty cycle

    def define_pin( self, *args ):
        # Called with ["midi"] entry of pinout.json
        return GPIOServoPin( self._period_us, self, *args )

class GPIOServoPin(RCServoPin):
    def __init__( self, *args ):
        super().__init__(*args )
        # start PWM with no pulse train, duty0 and duty1
        # are still undefined
        self._pwm = PWM( Pin(self._pin), 
                        freq=round(1_000_000/self._period_us),
                        duty_u16=0)

    
    def low_level_on( self ):
        super()._movement_start( )
        self._pwm.duty_u16( self._duty1 )

    def low_level_off( self ):
        super()._movement_start( )
        self._pwm.duty_u16( self._duty0 )

    def set_servopulse( self, pulse0_us, pulse1_us ):
        # Validate pulse0_us and pulse1_us
        super().set_servopulse( pulse0_us, pulse1_us )
        # Set duty cycle for "on" and "off" positions
        self._duty0 = round(pulse0_us/self._period_us*65536)
        self._duty1 = round(pulse1_us/self._period_us*65536)


    def stop_pwm( self ):
        # Stop PWM signal to lower power consumption and heat
        # Duty cycle 0 ceases PWM pulse train.
        self._pwm.duty_u16( 0 )
