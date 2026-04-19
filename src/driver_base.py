# Copyright (c) 2023-2025 Hermann von Borries
# MIT license
#  
from time import ticks_ms, ticks_diff, ticks_us
import asyncio
from actuatorstats import ActuatorStats

class BaseDriver:

    # The repr() of each driver MUST be unique
    # However, there will be one driver instance for GPIO
    # There will be one driver instance for each MCP23017 address
    # There will be one instance for each UART of MIDISerial
    # There will be one driver instance for each GPIO servo and period
    # There will be one instance for each PCA9685 address and period
    @classmethod
    def make_repr( cls, *args ):
        # make_repr allows solenoid.py to find a actuator based on characteristics
        # This is used for the actuator tests provided by the pinout.html page.
        # The format of the repr is for example:
        # MCP23017(0,32)
        # GPIOServo(5000,1000,1100)
        # i.e. the servername without "Driver" plus the part of the
        # constructor arguments that make the driver unique.
        return cls.__name__.replace("Driver", "") + str(args).replace(", ", ",").replace("()","")
    
    def __init__(self, *args ):
        self._repr = self.__class__.make_repr( *args )

    def __repr__( self ):
        return self._repr
    
    def __hash__( self ):
        return hash(self._repr)
    
    def __eq__( self, other):
        return self._repr == other._repr
    

class BasePin:
    # Abstract class for driver_*.py MIDI device actuator drivers
    # Represents a single pin/actuator 
    # used to drive a solenoid (subclass SolePin->subclasses GPIO pin, MCP23017 pin, MIDI over serial),
    # or RC controller (subclass RCServoPin->subclasses GPIO servo pin, PCA9685 servo pin)
    # or Virtual FTOM pin (subclass VirtualDrumPin)
    # in turn subclass SolePin or RCServoPin

    # BasePin._active_pins is a ordered list (oldest first)
    # of pins that are currently on. 
    # Used by subclass SolePin to calculate polyphony and
    # by driver_ftoms to see which pins are already on.
    
    # Integrates time solenoids are on or servos are moving
    # and consuming battery to make prediction of battery status.
    # Units: milliseconds of time solenoids/servos are consuming battery.
    is_solepin = False
    is_rcservo = False
    
    _battery_consumption = 0 # in msec

    # Blinking led to indicate exceptions like polyphony or
    # maximum moving servos exceeded. None = no blinking.
    led = None

    @classmethod
    def set_pinlist( cls, pin_list ):
        # ActuatorBank sets the complete pin list here, 
        # used in get_active() below.
        BasePin.pin_list = pin_list
    

    @classmethod
    def get_active( cls ):
        # Get generator over all active pins (of any kind, RC servo, sole, midi, etc except Null)
        return ( pin for pin in BasePin.pin_list if pin._current_value )

    @classmethod
    def set_led( cls, led ):
        # Inject led object, used by ActuatorBank, is changed
        # by all_notes_off, no led blinking there.
        cls.led = led 

    @classmethod
    def led_short_problem( cls ):
        if cls.led:
            cls.led.short_problem()

    def __init__( self, driver, pin, rank, nominal_midi_note ):
        # .name, .rank, .nominal_midi_note are read
        # as properties, no @property defined here to save a bit of space/overhead
        # _driver: the subclass of BaseDriver that created this pin.
        # _rank: supplied on pinout.html page, a text description
        # _pin: pin number, meaning depends on specific pin classs
        # nominal_midi_note: a NoteDef() object supplied on the pinout.html page
        # nominal_midi_number: note number of nominal_midi_note
        self._driver = driver
        self._pin = pin
        self._rank = rank  # >>> this takes 2600 bytes for 38 pins
        # nominal_midi_note and nominal_midi_number are used as (readonly) properties
        # outside this class.  
        self.nominal_midi_note = nominal_midi_note 
        # nominal_midi_number is redundant but convenient
        self.nominal_midi_number = nominal_midi_note.midi_number
        
        # self._count is the number of note_on received minus
        # the number of note_offs, but is never allowed to go negative.
        self._count = 0
        self._transition_time = ticks_ms() # is the last time when an actuator has been turned on or off
        # Current value, on or off.
        self._current_value = 0


    def on( self ):
        # Use self._count to match note on-note off pairs.
        if self._count == 0:
            # Turn on only when currently off, i.e. _count is 0
            # Check polyphony before adding another actuator.
            # Check moving RC pins before adding another actuator.
            if not self._actuator_change( 1 ):
                # Polyphony or RC moving limit exceeded, don't turn on (note on lost)
                return
            # Record time when pin was set on
            self._transition_time = ticks_ms()
            # Turn pin on (low level, implemented by subclass)
            self.low_level_on() # type: ignore

        # Count this "note on" event, to be able to pair note on/off
        # This also enables to turn off all pins that are on when pausing crank
        # or when the MIDI files ends or stops.
        self._count += 1
        self._current_value = 1

    def off( self ):
        # Set to off only when currently on and this the last note on
        # pending on this pin
        if self._count == 1:
            # Check constraints
            if not self._actuator_change( 0 ):
                # Moving limit exceeded, turning off postponed.
                return
            # Set pin to off (low level)
            self.low_level_off() # type: ignore
            # Accumulate the time the battery was used
            self._compute_battery_time()
            # Now record transition time
            self._transition_time = ticks_ms()
            
        # Do not allow count to go negative, meaning: ignore
        # if there are more note offs than note ons.
        self._count = max(0, self._count-1)
        self._current_value = 0

    def force_off( self ):
        # Force off, even if note on and note off don't match
        # but only if note is already on
        if self._count >= 1:
            self._count = 1
            self.off()

    def get_rank_name( self ):
        return self._rank
    
    def __repr__( self ):
        # Must be unique per pin!!!!
        return  f"{repr(self._driver)}.{self._pin}"

    @classmethod
    def get_reset_battery_usage( cls ):
        z = round(cls._battery_consumption)
        cls._battery_consumption = 0
        return z  

    def _actuator_change( self, new_value ):
        # Checks if actuator movement is allowed (polyphony, max rc servos moving)
        # Subclasses may override this method. False=suppress current movement.
        return True

    def _compute_battery_time( self ):
         # Subclasses will override this method
        pass

    def set_servopulse( self, pulse0_us, pulse1_us ):
        # Subclasses may override this method
        # Sets pulse with for ON and OFF states for RC servos.
        pass

    def __hash__( self ):
        return hash( repr(self) )
    
    def __eq__( self, other ):
        return repr(self) == repr(other)
    
    
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
        # Inject configuration
        cls.config_max_polyphony = max( config.max_polyphony, 1)

    @classmethod
    def clear_active( cls ):
        # When doing all notes off, reset
        SolePin.sole_polyphony = 0
        
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

class RCServoPin(BasePin):
    # Abstract class to derive RC Servo classes GPIOServoPin and PCA9685ServoPin
    # Subclasses must implement:
    #   1. __init__() including super().__init__()
    #   2. low_level_on() and low_level_off() calling _movement_start()
    #   3. set_servopulse() calling super().set_servopulse()
    #   4. stop_pwm()
    is_rcservo = True

    # Count of pins that are moving
    _global_moving = 0

    @classmethod
    def set_config( cls, config ):
        # Set by ActuatorBank for all RC pins
        cls.config_rc_moving_time = config.rc_moving_time
        cls.config_rc_pwm_auto_off = config.rc_pwm_auto_off
        cls.config_rc_max_moving = config.rc_max_moving

    def __init__( self, period_us, *args ):
        super().__init__( *args )
        self._period_us = period_us
        # Counter if this pin is currently moving
        self._this_moving = 0
        # Simulate that the RC Servo is on,
        # so the first call to controller.all_notes_off() will
        # move all servos to the off position and
        # then (if so configured turn off PWM 
        self._count = 1

    def _movement_start( self ):
        # A servo movement is about to start
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
        # To be completed by the subclass. Servo pulse width is in microseconds
        # and can is set individually for each RC servo pin.
        if not( 1000 <= pulse0_us <= 2000 and 1000 <= pulse1_us <= 2000 ):
            raise ValueError("Pulse width must be between 1000 and 2000")

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
