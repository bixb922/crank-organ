# Copyright (c) 2023-2025 Hermann von Borries
# MIT license
#  
from time import ticks_ms

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
        # and allows pinout.py's driver factory to have only one object for
        # a driver with the same args.
        # The format of the repr is for example:
        # "GPIO"
        # "MCP23017(0,0x20)""
        # "GPIOServo(1000,1100)"
        # i.e. the servername without "Driver" plus the part of the
        # constructor arguments that make the driver onject unique.
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
    
    # Memory usage 400 bytes per pin all included (dictionaries
    # or lists conaining pins, keys, etc)
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

    # async _check_stuck_notes( cls):
    #   _MAX_ON_MS = const(2000)
    #   while True:
    #       await asyncio.sleep_ms(1000)
    #       now = ticks_ms()
    #       for p in cls.get_active():
    #           if ticks_diff( now, p._transition_time()) > _MAX_ON_MS:
    #               p.force_off()
    #               ActuatorStats.count("stuck notes")
    #

    @classmethod
    def set_led( cls, led ):
        # Inject led object
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
        self._rank = rank
        self.nominal_midi_note = nominal_midi_note 
        
        # self._count is the number of note_on received minus
        # the number of note_offs, but is never allowed to go negative.
        self._count = 0
        self._transition_time = ticks_ms() # is the last time when an actuator has been turned on or off
        # Current value, on or off 
        self._current_value = 0

    @property
    def nominal_midi_number( self ):
        return self.nominal_midi_note.midi_number
    
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
            self._movement_start()
            self.low_level_on() # type: ignore

        # Count this "note on" event, to be able to pair note on/off
        # This also enables to turn off all pins that are on when pausing crank
        # or when the MIDI files ends or stops.
        self._current_value = 1
        self._count += 1



    def off( self ):
        # Set to off only when currently on and this the last note on
        # pending on this pin
        if self._count == 1:
            # Check constraints
            if not self._actuator_change( 0 ):
                # Moving limit exceeded, turning off postponed.
                return
            # Set pin to off (low level)
            self._movement_start()
            self.low_level_off() # type: ignore

            # Accumulate the time the battery was used
            self._compute_battery_time()
            # Now record transition time
            self._transition_time = ticks_ms()
            
        # Do not allow count to go negative, meaning: ignore
        # if there are more note offs than note ons.
        self._count = max(0, self._count-1)
        self._current_value = 0
        # It's not a good idea to let _count <0.
        # When crank stops, there may be a note off with note
        # on. That note will never sound again during the MIDI file


    def force_off( self ):
        # Force off, even if note on and note off don't match
        # but only if note is already on.
        if self._count >= 1:
            self._count = 1
            self.off()

    def get_rank_name( self ):
        return self._rank
    
    def __repr__( self ):
        # Must be unique per pin within a driver!!!!
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

    def _movement_start(self):
        # RC Servos override this to keep track of moving servos
        # for current consumption
        pass

    def __hash__( self ):
        return hash( repr(self) )
    
    def __eq__( self, other ):
        return repr(self) == repr(other)
    

