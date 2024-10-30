# (c) 2023 Hermann Paul von Borries
# MIT License
# MIDI note class and MIDIdict.
# The MIDI note class and MIDIdict allow MIDI notes with a "any" program number
# That eases the configuration for simple crank organs, but allows
# sophisticated configuration of MIDI notes addressable with program numbers
# and percussion (drums) channel support.
# MIDIdict is a dictionary that allows search efficiently for a MIDI Note.

# Also included: some functions to get note names, frequency, cents


from math import log
from machine import Pin
import asyncio
from collections import OrderedDict
import time
import machine

from config import config
import fileops

# Some useful functions related to MIDI
_NOTE_LIST = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")

# Define the MIDI channel number for Drums (set by GM standard)
DRUM_CHANNEL = 9 # MIDI channel 10 (physical=9)

# Definitions for NoteDef
DRUM_PROGRAM = 129
WILDCARD_PROGRAM = 0 # Must be zero, see basic_note_on/basic_note_off


class NoteDef:
    # Note definition: this class is used to store note definitions
    # done on the pinout.html page and parsed by pinout.py.
    # MIDI notes that are retrieved from MIDI files  are never instantiated as NoteDef.
    def __init__(self, program_number, midi_number):
        # Instrument can be:
        #   program number 1-128 (not 0-127!!!!)
        #   DRUM_PROGRAM (129) for drum channel 10
        #   WILDCARD_PROGRAM (0) any MIDI program number from 1-128
        # If program_number is None, then it means: WILDCARD_PROGRAM
        # If midi_number is None, then this note is undefined (this
        # happens only if midi number field is left blank on the user interface)
        # If program_number is None, set to WILDCARD_PROGRAM
        self.program_number = program_number or WILDCARD_PROGRAM
        self.midi_number = midi_number
        # self.program_number and self.midi_number are accessed as if
        # they were properties, no @property (it's faster, less code)

    def __str__(self):
        if self.midi_number is None:
            return ""
        
        if self.program_number == WILDCARD_PROGRAM:
            instr = ""
        elif self.program_number == DRUM_PROGRAM:
            instr = f"Dr{self.program_number}-"
        else:
            # instr = f"{GM_PROGRAM[self.program_number]}({self.program_number})-"
            instr = f"P{self.program_number}-"

        return f"{instr}{self.note_name()}({self.midi_number})"
    
    def __repr__(self):
        return str(self)

    def frequency(self):
        return 440 * 2 ** ((self.midi_number - 69) / 12)

    def cents(self, measured_freq):
        if not measured_freq or measured_freq <= 0:
            return None
        return 1200 * log(measured_freq / self.frequency()) / log(2)

    def note_name(self):
        if not self.is_valid():
            return ""
        if self.program_number == DRUM_PROGRAM:
            return str(self.midi_number)
        return _NOTE_LIST[self.midi_number % 12] + str((self.midi_number // 12) - 1)

    def is_valid( self ):
        return self.midi_number is not None
    
    def is_correct( self ):
        correct = True
        if self.midi_number is not None:
            correct = correct and 0 <= self.midi_number <= 127
        if self.program_number is not None:
            correct = correct and WILDCARD_PROGRAM <= self.program_number <= DRUM_PROGRAM
        return correct
    
class Register:
    def __init__( self, name ):
        self.name = name
        self.current_value = 0
        if not name:
            # The only software register to start on
            # is the "always on" default register
            # or set_initial_value
            self.current_value = 1

    def set_gpio_pin( self, gpio_number ):
        # Update gpio pin only of not defined already
        # This allows some flexibility in the order of 
        # the definition.
        # if name is "", no gpio should be defined
        if self.name == "" and gpio_number:
            raise ValueError
        # First gpio defined for a register is the valid one
        if gpio_number:
            pin = Pin( gpio_number, Pin.IN, Pin.PULL_UP )
            self.register_task = asyncio.create_task( self._register_process( pin ))
        # If no gpio_number supplied, don't change anything.

    def set_initial_value( self, initial_value ):
        self.current_value = initial_value

    def value( self ):
        return self.current_value
    
    async def _register_process( self, pin  ):
        last_value = pin.value()
        while True:
            # Poll frequently, but not too frequently,
            # to have good response time but a stable value
            # 100 ms is well within fast response time perception
            # but should give enough time for debouncing.
            await asyncio.sleep_ms(200)
            pv = pin.value()
            if pv != last_value:
                # Change seen on hardware switch,
                # record current value
                self.current_value = (1-pv)
                # However, web interface can change this again via
                # toggle() function below
                last_value = pv

    def toggle( self ):
        # Change register from 1 to 0 and from 0 to 1, called from web interface
        # via /register_toggle to change the current value
        # It also can then be set via GPIO and then it follows 
        # the hardware switch
        self.current_value = 1 - self.current_value



class RegisterBank:
    # Register class factory, also holds all defined Register objects
    def __init__( self ):
        self.register_dict = OrderedDict()

    def factory( self, name ):
        try:
            return self.register_dict[name]
        except KeyError:
            reg = Register( name )
            self.register_dict[name] = reg
        return reg
    
    def complement_progress( self, progress ):
        # Return all register names and values (for UI)
        progress["registers"] = [ 
            (r.name, r.value()) 
            for r in self.register_dict.values() if r.name]
        return progress
    
    def get_register( self, name ):
        return self.register_dict[name]
    
class Controller:
    def __init__( self ):

        # solenoids driver object is defined later by set_solenoid_driver()
        self.solenoids = None 

        # The key of the note dictionary is self.make_notedict_key()
        # The contents at this key is the list of solenoid pins/registers
        # for this note number
        self.notedict = {}

    def make_notedict_key( self, program_number, midi_number ):
        # assert WILDCARD_PROGRAM <= program_number <= DRUM_PROGRAM
        # assert 0 <= midi_number <= 127
        return program_number*256 + midi_number
    
    def get_actions( self, program_number, midi_number ):
        # Use program number in the key. If this does not work,
        # use WILDCARD_PROGRAM. If that doesn't work either,
        # return a empty list (no note will sound) 
        return self.notedict.get( self.make_notedict_key( program_number,  midi_number), 
               self.notedict.get( self.make_notedict_key(WILDCARD_PROGRAM, midi_number), []))
    
    def set_solenoid_driver( self, solenoids ):
        self.solenoids = solenoids
    
    def define_start( self ):
        self.notedict = {}

    def define_note( self, note, solepin, register_name="" ):
        register = registers.factory( register_name )
        program_number = note.program_number
        midi_number = note.midi_number
        # Add to a list of notes to sound for each note.        
        actions = self.notedict.setdefault(self.make_notedict_key(program_number, midi_number), [] )
        actions.append( ( solepin, register, note ) )

    def define_complete( self ):
        # Solenoid definitions have now been just parsed.
        # Drums are not controlled by a register, use "always on" register.
        register = registers.factory( "" )
        # Add simulated drum notes if no drums defined via the pinout.html page
        # There is a recursion of one level here: the simulated drum notes
        # in turn are composed again of midi notes.
        for drum in SimulatedDrums( self.solenoids ):
            key = self.make_notedict_key(DRUM_PROGRAM, drum.midi_number )
            # Check if there is already a drum defined via pinout page
            # If not, define drum pointing to the simulated drum
            self.notedict.setdefault( key, [( drum, register, drum.midi_note )] )
        return
    
    def note_on( self, program_number, midi_number ):
        # assert WILDCARD_PROGRAM<=program_number <=DRUM_PROGRAM
        # assert 0<=midi_number<= 127 
        # Get list of actions (i.e. Solepin objects subject to registers) 
        # to activate for this midi note
        actions = self.get_actions( program_number, midi_number )
        for solepin, register, _ in actions:
            if register.value():
                solepin.on()
        # Return truish to caller if a note was played
        return actions           

    def note_off( self, program_number, midi_number ):
        # assert 1<=program_number <=128 
        # assert 0<=midi_number<= 127
        # Get list of solenoid pins to turn off for this midi note
        actions = self.get_actions( program_number, midi_number )
        for p in actions:
            # p[0] is the solepin/drum object, p[1] the register (not needed here), p[2] the NoteDef
            p[0].off()

    def all_notes_off( self ):
        # Proxy to solenoids.all_notes_off(). 
        # Turn off all pins, this is better
        # than turning off all midi notes.
        self.solenoids.all_notes_off()

    def reinit( self ):
        # Called to reinitialize controller when pinout.html informs
        # that the pinout has to be saved/changed.
        global controller, registers
        controller = Controller()
        registers = RegisterBank()

    def get_notedict(self):
        # Used by webserver to list pinout
        return self.notedict

class SimulatedDrums:
    def __init__( self, solenoids ):
        temp_def = fileops.read_json( config.DRUMDEF_JSON, default={})
        # Need the midi numbers used as key be an int
        self.drum_def = dict( 
            (int(midi_number), dd) 
            for midi_number,dd in temp_def.items() )

        # Store the solenoid driver to be called directly for drum activation
        self.solenoids = solenoids

    # Provide iterator for all defined drums
    def __iter__( self ):
        self.iter_drums = iter(self.drum_def.items())
        return self
    
    def __next__( self ):
        # Return a new Drum() object for each iteration
        midi_number, dd = next( self.iter_drums )
        return Drum( midi_number, dd, self.solenoids )

    
class Drum:
    # Must have same interface as solenoids.Solepin() except __init__
    def __init__( self, midi_number, drumdef, solenoids ):
        # Same attributes as Solepin()
        self.name = drumdef["name"]
        self.rank = "Simulated drum"
        self.pin_function = lambda _: None # Null function
        self.midi_note = NoteDef( DRUM_PROGRAM, midi_number )
        self.midi_number = midi_number
        self.on_time = -1

        # Store duration, solenoid driver, and the cluster of valves
        # to activate if a Simulated Drum note is played
        self.duration = drumdef["duration"]*1000
        self.strong_added =  (drumdef["strong_duration"] -  drumdef["duration"])*1000
        self.solenoids = solenoids
        self.midi_solepins = set() # of solepins
        for midi_number in drumdef["midi_list"]:
            actions = controller.get_actions( WILDCARD_PROGRAM, midi_number )
            if actions:
                # Add solepin of this midi number to cluster
                # actions[0] is the first definition for this midi_number
                # actions[0] is the solepin for the first midi number
                self.midi_solepins.add( actions[0][0] )
        self.strong_midi_solepins = set()
        for midi_number in drumdef["strong_midis"]:
            actions = controller.get_actions( WILDCARD_PROGRAM, midi_number )
            if actions:
                self.strong_midi_solepins.add( actions[0][0] )



    # Important restriction: cannot play two drum notes simultaneusly
    # They will play one after the other
    def on( self ):
        # Simulate a drum note without disturbing other notes that may be on
        sole_on = self.solenoids.solepins_that_are_on()
        solepin_list = self.midi_solepins - sole_on
        strong_solepin_list = self.strong_midi_solepins - sole_on
        # Sound all notes in the cluster
        for solepin in strong_solepin_list:
            solepin.on()
        for solepin in solepin_list:
            solepin.on()
        # Wait here to get the time right.
        # This time is short (durtion should be <= 50 milliseconds)
        # Don't use asyncio.sleep_ms because time will be not
        # controllable and the time is really too short to do other stuff. 
        # Duration of the drum note is the highest priority here.

        time.sleep_us( self.duration )
        for solepin in solepin_list:
            solepin.off()
        # Wait a bit to turn of stronger (accented) notes
        time.sleep_us( self.strong_added )
        for solepin in strong_solepin_list:
            solepin.off()


    def off( self ):
        # Drum note has already been turned off in on() function
        return
    
    def is_on( self ):
        # Never seen "on"
        return False
 
    def get_rank_name( self ):
        return self.name + " " + self.rank

# MIDI over serial (UART) driver
class MidiSerial:
    # Initialize UART. UART number can be 1 or 2 for the ESP32
    # (see https://docs.micropython.org/en/latest/esp32/quickref.html)
    # since UART 0 is used for REPL.
    # Pin is the GPIO output pin number
    # Channel is the MIDI channel number assigned to all notes
    # when played
    def __init__( self, uart, pin, channel ):
        # Default rx is 9
        self.uart = machine.UART( uart, baudrate=31250, tx=pin )
        # Have bytearray with the command ready, format is:
        # event+channel, note, velocity
        self.note_on = bytearray( (0x90 + channel, 0,127))
        self.note_off = bytearray((0x80 + channel, 0,  0))

    # Only note on/note off messages are sent
    def note_message( self, midi_note, note_on ):
        print(">>>", midi_note, note_on)
        if note_on:
            self.note_on[1] = midi_note.midi_number
            self.uart.write( self.note_on )
        else:
            self.note_off[1] = midi_note.midi_number
            self.uart.write( self.note_off )

controller = Controller()
registers = RegisterBank()
