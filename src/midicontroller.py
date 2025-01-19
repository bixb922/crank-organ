# Copyright (c) 2023 Hermann von Borries
# MIT license

from machine import Pin
import asyncio
from collections import OrderedDict
from random import randrange

from driver_ftoms import FauxTomDriver
from midi import  DRUM_PROGRAM, WILDCARD_PROGRAM


class Register:
    def __init__( self, name ):
        self.name = name
        # The only software register to start on
        # is the "always on" default register
        # with name "" 
        self.current_value = not name

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
        self.current_value = bool(initial_value)

    def value( self ):
        return bool(self.current_value)
    
    async def _register_process( self, pin  ):
        last_value = pin.value()
        while True:
            # Poll frequently, but not too frequently,
            # to have good response time but a stable value
            # 100-200 ms is well within fast response time perception
            # but should give enough time for debouncing.
            await asyncio.sleep_ms(100)
            pv = pin.value()
            # Change only if someone moved the switch.
            # This allows to recognize both
            # a hardware switch and
            # the checkbox on the play.html page
            if pv != last_value:
                # However, web interface can change this again via
                # set_value() function below
    
                self.set_value( not pv )
                last_value = pv

    def set_value( self, new_value ):
        self.current_value = new_value

# Class for all registers
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
    

class MIDIController:
    # The MIDI controller takes care of MIDI note on
    # and note off events, heeding registers
    # and drum notes, and sending note on and off events
    # to the actuator drivers.
    def __init__( self, registers ):
        self.registers = registers
        # The main data structure here is self.notedict
        # The key of the note dictionary is self.make_notedict_key()
        # The contents at this key is the list of actions
        # solenoid pins/registers
        # Each action is a 4-tuple:
        #   a pin or virtual pin (that can be set .on() or .off())
        #   a register (to get it's .value())
        #   the nominal midi note (a NoteDef object) 
        #   the invert indicator (False=don't invert, True=invert)
        #
        self.notedict = {}

    def make_notedict_key( self, program_number, midi_number ):
        # assert WILDCARD_PROGRAM <= program_number <= DRUM_PROGRAM
        # assert 0 <= midi_number <= 127
        return program_number*256 + midi_number
    
    def add_action( self, actuator, register_name, midi_note ):
        invert = False
        if register_name.startswith("~"):
            invert = True
            register_name = register_name[1:]
        reg = self.registers.factory( register_name )
        # Add an action to the program_number/midi_number pair
        # (program number may be WILDCARD_PROGRAM or DRUM_PROGRAM too)
        key = self.make_notedict_key( midi_note.program_number, midi_note.midi_number )
        actions = self.notedict.setdefault( key, [] )
        actions.append( (actuator, reg, midi_note, invert ) )


    def get_actions( self, program_number, midi_number ):
        # Use the note's program number in the key. If this does not work,
        # use WILDCARD_PROGRAM. If that doesn't work either,
        # return a empty list (no note will sound) 
        return self.notedict.get( self.make_notedict_key( program_number,  midi_number), 
               self.notedict.get( self.make_notedict_key(WILDCARD_PROGRAM, midi_number), []))

    def define_start( self ):
        self.notedict = {}

    def define_note( self, midi_note, actuator, register_name="" ):  
        self.add_action( actuator, register_name, midi_note )


    def define_complete( self, actuator_bank ):
        self.actuator_bank = actuator_bank

        # Physical valve pin definitions have now been just parsed.

        # Faux Toms are not controlled by a register, use "always on" register.
        # Add simulated drum notes if no drums defined via the pinout.html page
        # There is a recursion of one level here: the simulated drum notes
        # in turn are composed again of midi notes.
        # Faux Bass driver deleted, ugly sound.
        # for driver in [ FauxTomDriver(), FauxBassDriver() ]:
        driver = FauxTomDriver()
        driver.set_actuator_bank( actuator_bank )
        for virtual_pin in driver:
            self.add_action( virtual_pin, "", virtual_pin.nominal_midi_note )
        return
         
    def note_on( self, program_number, midi_number ):
        # assert WILDCARD_PROGRAM<=program_number <=DRUM_PROGRAM
        # assert 0<=midi_number<= 127 
        # Get list of actions (i.e. Solepin objects subject to registers) 
        # to activate for this midi note
        actions = self.get_actions( program_number, midi_number )
        for actuator, register, _, invert in actions:
            if register.value() != invert:
                actuator.on()
        # Return truish to caller if a note was played
        return actions           

    def note_off( self, program_number, midi_number ):
        # assert 1<=program_number <=128 
        # assert 0<=midi_number<= 127
        # Get list of  pins to turn off for this midi note
        actions = self.get_actions( program_number, midi_number )
        for p in actions:
            # p[0] is the pin or virtual pin object
            # Don't check register here, no damage in turning off
            # a note.
            p[0].off()

    def all_notes_off( self ):
        self.actuator_bank.all_notes_off()

    async def play_random_note(self, duration_msec):
        if not hasattr( self, "all_midis" ):
            self.all_midis = [ 
                ( n//256, n&256) 
                for n in self.notedict.keys() 
                if n//256 != DRUM_PROGRAM ]
        n =  len(self.all_midis)
        if n:
            program_number, midi_number = self.all_midis[ randrange( 0, n ) ]
            self.note_on( program_number, midi_number )
            await asyncio.sleep_ms(duration_msec)
            self.note_off( program_number, midi_number )

    async def clap(self, n):
        for _ in range(n):
            await self.play_random_note(50)


    def get_notedict(self):
        # Used by webserver to list pinout
        return self.notedict

