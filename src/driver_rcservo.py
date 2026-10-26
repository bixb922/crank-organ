import asyncio
from time import sleep_ms
from driver_base import BasePin, BaseDriver
from actuatorstats import ActuatorStats

# Abstract driver superclass to PCA9685Driver and GPIOServoDriver
class RCServoDriver(BaseDriver):
    def all_servos_off(self, pin_list):
        # Common for RC Servos, checking battery configuration limits
        # Doesn't need asyncio, so can be used in non-asyncio contexts.
        # Will return all servos to "off" position, checking that battery
        # consumption is not exceeded.
        # Wait for previous movements to settle
        sleep_ms(RCServoPin.config_rc_moving_time )
        i = 0
        for pin in pin_list:
            if pin.is_rcservo:
                # Always turn off. This ensures "off" position
                # at startup too. If already off, no movement will
                # take place and that is good.
                pin.low_level_off()
                i += 1
                if i % RCServoPin.config_rc_max_moving == 0:
                    # Ensure that battery current stays within range.
                    sleep_ms(RCServoPin.config_rc_moving_time )
        # Wait for remaining servos to settle
        sleep_ms(RCServoPin.config_rc_moving_time )
        # force_off will not move servo, since we have done that already.
        # But force_off() will set pin._count, pin._current_value
        # and (eventually, when async kicks in) RCServoPin._global_moving correctly.
        for pin in pin_list:
            if pin.is_rcservo:
                pin.force_off()  
        # Don't force  RCServoPin._global_moving here, because there may
        # be _wait_movement_end() tasks pending.


# Abstract RC Servo pin driver, superclass to PCA9685 and GPIOServoPin
class RCServoPin(BasePin):
    # Abstract class to derive RC Servo classes GPIOServoPin and PCA9685ServoPin
    # Subclasses must implement:
    #   1. __init__() including super().__init__()
    #   2. low_level_on() and low_level_off() 
    #   3. set_servopulse() calling super().set_servopulse()
    #   4. stop_pwm()
    is_rcservo = True

    # Count of pins that are moving
    _global_moving = 0

    @classmethod
    def set_config( cls, config ):
        # Set by ActuatorBank for all RC pins at the superclass level
        # for all subclasses
        RCServoPin.config_rc_moving_time = config.rc_moving_time
        RCServoPin.config_rc_pwm_auto_off = config.rc_pwm_auto_off
        RCServoPin.config_rc_max_moving = config.rc_max_moving

    def __init__( self, period_us, *args ):
        super().__init__( *args )
        self._period_us = period_us
        # Counter if this pin is currently moving
        self._this_moving = 0
        self._count = 0

    def _movement_start( self ):
        # A servo movement is about to start. Called by pin.on() and pin.off()
        # RCServoPin._global_moving is a counter of all currently moving servos
        if self._this_moving == 0: 
            # Count only when self._this_moving goes from 0 to 1
            # to include case of very close movements
            RCServoPin._global_moving += 1
        self._this_moving += 1
        # Launch task to time when movement has finished
        asyncio.create_task( self._wait_movement_end() )

    async def _wait_movement_end( self ):
        # Wait for servo movement to finish.

        # self._wait_movement_end() will take about 1% of the CPU
        # Having a unique background job for all pins will also take about 1% of CPU
        # but this design distributes the time in very small tasks 
        # which is even nicer for asyncio

        await asyncio.sleep_ms( self.config_rc_moving_time )
        # self._this_moving should never go below zero, since +1 and -1 are always paired by this code here.
        self._this_moving -= 1
        if self._this_moving == 0:
            # Any overlapping movements of this pin have stopped now
            # One servo less moving.
            RCServoPin._global_moving -= 1
            if self.config_rc_pwm_auto_off and not self._current_value:
                # Actuator state is off and movement has stopped, no servo force necessary.
                self.stop_pwm() # type:ignore

    def _compute_battery_time( self ):
        # 2 movements, on and off, battery is used only when RC Servo moves.
        # If there is a mix of solenoids and RC servos, this
        # will not be very precise.
        BasePin._battery_consumption += 2 * RCServoPin.config_rc_moving_time

    def set_servopulse( self, pulse0_us, pulse1_us ):
        from drehorgel import config
        # To be completed by the subclass. Servo pulse width is in microseconds
        # and can is set individually for each RC servo pin.
        if not( config.rc_min_pulse <= pulse0_us <= config.rc_max_pulse and 
                config.rc_min_pulse <= pulse1_us <= config.rc_max_pulse ):
            raise ValueError(f"Pulse width must be between {config.rc_min_pulse} and {config.rc_max_pulse}")

    def _actuator_change( self, new_value ):
        # Limit the maximum of moving servos (both turning on and off)
        # Polyphony does not apply for RC servos 
        # Return True=ok to move, False=don't start movement.

        # It is about the same overhead if _global_moving
        # is calculated each time here using _transition_time
        # (without turning off servos when not moving)
        moving_servos = RCServoPin._global_moving 

        ActuatorStats.max( "max moving servos", moving_servos ) 

        # Restrict movement of servos if some limit exceeded
        if (moving_servos > RCServoPin.config_rc_max_moving):
            BasePin.led_short_problem()
            ActuatorStats.count( "rc exceeded moving" ) 
            # For on: suppress movement
            # for off: delay movement (and suppress current movement)
            if not new_value:
                asyncio.create_task( self._delayed_off( self.config_rc_moving_time ))
            # Return False means "supress movement"
            return False
        return True
    
    async def _delayed_off( self, t ):
        # Delay RC servo off movement by about t milliseconds, used by self._actuator_change()
        await asyncio.sleep_ms( t )
        # Using pin.off() will enable check _actuator_change again after this delay.
        # That means that a note_off could be delayed several times.
        self.off()

# Exception processing pinout file for line ['midi', 7, '', 79, '17 G violin G5', ''] Pulse width must be between 1000 and 2000
# Traceback (most recent call last):
#   File "main.py", line 41, in <module>
#   File "asyncio/core.py", line 1, in run
#   File "asyncio/core.py", line 1, in run_until_complete
#   File "asyncio/core.py", line 1, in run_until_complete
#   File "crank-organ/src/startup.py", line 204, in start
#   File "crank-organ/src/drehorgel.py", line 74, in init
#   File "crank-organ/src/pinout.py", line 674, in __init__
#   File "crank-organ/src/pinout.py", line 103, in __init__
#   File "crank-organ/src/pinout.py", line 180, in parse
#   File "crank-organ/src/pinout.py", line 170, in <lambda>
#   File "crank-organ/src/pinout.py", line 772, in define_midi
#   File "crank-organ/src/driver_pca9685.py", line 72, in set_servopulse
#   File "crank-organ/src/driver_base.py", line 317, in set_servopulse
# ValueError: Pulse width must be between 1000 and 2000

