from driver_base import BasePin, BaseDriver
from actuatorstats import ActuatorStats
from time import ticks_diff, ticks_ms

class SoleDriver(BaseDriver):
    def all_sole_off(self, driver_list, pin_list):
        # Turn notes off wholesale if possible
        for drv in driver_list:
            if hasattr(drv, "fast_off"):
                drv.fast_off()
        # Turn off the rest, and for those already turned off
        # update pin._count, pin._current_value and 
        # SolePin.sole_polyphony.
        for pin in pin_list: 
            if pin.is_solepin:
                pin.force_off()
        assert SolePin.sole_polyphony == 0 # >>>
        SolePin.sole_polyphony = 0



class SolePin(BasePin):
    # Superclass for all drivers that move solenoids
    # Subclasses must implement:
    #   __init__() calling super().__init__()
    #   low_level_on() and low_level_off()
    is_solepin = True

    # Management of maximum solenoids that can be on
    sole_polyphony = 0 
    # Configuration parameter for polyphony
    config_max_polyphony = 10

    @classmethod
    def set_config( cls, config ) :
        # Set by ActuatorBank for all SolePin pins.
        # Inject configuration at the superclass level,
        # for all subclasses
        SolePin.config_max_polyphony = max( config.max_polyphony, 1)

    def _compute_battery_time( self ):
        BasePin._battery_consumption += ticks_diff(ticks_ms(), self._transition_time)     
        
    # Actuator_change for solenoid pins
    # There is a different code for RC servos.
    def _actuator_change( self, new_value ):
        if new_value:
            while SolePin.sole_polyphony >= SolePin.config_max_polyphony:
                ActuatorStats.count( "exceeded polyphony" )
                try:
                    # Find oldest active solenoid pin
                    oldest_pin = min( pin for pin in BasePin.get_active() if pin.is_solepin )
                    oldest_pin.force_off()
                except ValueError:
                    # No active pins, but then, why is SolePin.sole_polyphony != 0?
                    SolePin.sole_polyphony = 0
                    break
            SolePin.sole_polyphony += 1
        else:
            SolePin.sole_polyphony -= 1
        ActuatorStats.max( "max polyphony", SolePin.sole_polyphony )
         # Any polyphony problem has been taken care of, now turn on current note
        return True

    def __lt__( self, other ):
        # pin1 < pin2 iff pin1 moved before pin2
        # For use only over BasePin.get_active() iterator
        # with the min() funcion to find the oldest active pin
        return ticks_diff( self._transition_time,  other._transition_time ) < 0 
