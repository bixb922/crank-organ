# Copyright (c) 2023-2025 Hermann von Borries
# MIT license

from machine import Pin
import asyncio
from collections import OrderedDict
from random import choice

from midi import  DRUM_CHANNEL, DRUM_PROGRAM, NoteDef
from umidiparser import NOTE_OFF, NOTE_ON, PROGRAM_CHANGE
from actuatorstats import ActuatorStats

# Allocate a NoteDef once (instead of creating a new one for each note on and off event) to avoid
CURRENT_NOTE = NoteDef(0,0)

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
            # If gpio_number is invalid, pinout.py will trap 
            # the exception and skip the register definition
            register_gpio = Pin( gpio_number, Pin.IN, Pin.PULL_UP )
            self.register_task = asyncio.create_task( self._register_process( register_gpio ))
        # If no gpio_number supplied, don't change anything.

    def set_initial_value( self, initial_value ):
        self.current_value = bool(initial_value)

    def value( self ):
        return bool(self.current_value)
    
    async def _register_process( self, register_gpio  ):
    # registers disabled for now
        last_value = register_gpio.value()
        while True:
            # Poll frequently, but not too frequently,
            # to have good response time but a stable value
            # 100-200 ms is well within fast response time perception
            # but should give enough time for debouncing.
            await asyncio.sleep_ms(100)
            pv = register_gpio.value()
            # Change only if someone moved the switch.
            # This allows to recognize both
            # a hardware switch and
            # the checkbox on the play.html page
            if pv != last_value:
                # However, web interface can change this again via
                # set_value() function below
    
                self.set_value( not pv )
                last_value = pv
    
    def set_controller( self, controller ):
        self.controller = controller 

    def set_value( self, new_value ):
        self.current_value = new_value
        if new_value == 0 and self.name:
            self.controller._all_off_for_register( self.name )
        
# Class for all registers
class RegisterBank:
    # Register factory, holds all defined Register objects
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
    
    def set_midicontroller( self, controller ):
        # Set the MIDI controller for all registers
        # This is done here to avoid circular imports
        # and to keep the register class simple
        for reg in self.register_dict.values():
            reg.set_controller( controller )

class MIDIController:
    # The MIDI controller takes care of MIDI note on
    # and note off events, heeding registers
    # and drum notes, and sending note on and off events
    # to the actuator drivers.
    def __init__( self, register_bank ):
        self.register_bank = register_bank
        # The main data structure here is self.notedict
        # The key of the note dictionary is a NoteDef
        # The contents at this key is the list of actions
        # Each action is a 3-tuple:
        #   a pin or virtual pin that can be set .on() or .off()
        #   a register (to get it's .value())
        #   the nominal midi note (a NoteDef object) 
        #
        self.notedict = {}

        # Passthrough driver callback (ex: for a synthesizer)
        # There can be only one (i.e. not a list)
        self.passthrough = None

        # Program number per channel
        # 1 to 128. Channel 10 always has DRUM_PROGRAM (129)
        self.channelmap1 = bytearray(16)

    # Methods called by pinout to define what actuators to command for
    # each note
    def define_start( self ):
        self.notedict = {}

    def define_note( self, midi_note, actuator, register_name="" ):  
        reg = self.register_bank.factory( register_name )
        # Add an action to midi_note
        # Midi note may have program_number equal to
        # WILDCARD_PROGRAM or DRUM_PROGRAM
        actions = self.notedict.setdefault( midi_note, [] )
        # Append on/off methods to be fast. 
        # Append register because it's needed to govern notes
        # Append actuator only for webserver.list_by_midi_note()
        actions.append( (actuator.off, actuator.on, reg, actuator ))

    def define_passthrough( self, callback ):
        self.passthrough = callback
    
    def define_complete( self, actuator_bank ):
        self.actuator_bank = actuator_bank

        # Solenoid/RC MIDI definitions (pinout.json) have now been just parsed.

        # Add simulated drum notes if no drums defined via the pinout.html page
        # There is a recursion of one level here: the simulated drum notes
        # in turn are composed again of midi notes.
        from driver_ftoms import FauxTomDriver
        # define_complete is only called once, no need to check that
        # FauxTomDriver is called twice.
        for virtual_pin in FauxTomDriver( actuator_bank ):
            # Faux Toms are not controlled by a register, use "always on" register.
            self.define_note( virtual_pin.nominal_midi_note, virtual_pin, "" )
        self.register_bank.set_midicontroller( self )
         
    def _get_actions( self, midi_note ):
        # Use the note's program number in the key (specific search). 
        # If this does not work,
        # use WILDCARD_PROGRAM in the key to match
        # midi note definitions in pinout with wildcard program number.
        # If that doesn't work either, return a empty list (no note will sound) 
        return self.notedict.get( midi_note, 
               self.notedict.get( midi_note.wildcard(), []))


    def file_start( self, midifile ):
        # player.py calls this at start of a MIDI file
        # midifile is a umidiparser.MidiFile object.
        for i in range(16):
                self.channelmap1[i] = 1 # Default: piano
        self.channelmap1[DRUM_CHANNEL] = DRUM_PROGRAM   

        self.process_map = {
            NOTE_ON: self._note_event_on,
            NOTE_OFF: self._note_event_off,
            PROGRAM_CHANGE: self._program_change,
        }

        f = midifile.format_type
        if f in (0,1,0xd0):
            if f == 0xd0:
                self.process_map[0xd0] = self.processd0
            return
        
        raise ValueError(f"Unknown MIDI file format {midifile.format_type}")

    def process_midi( self, midi_event ):
        # Process all MIDI events as passed by player.
        # Called with channel, meta and sysex events 
        # Meta events are ignored
        status = midi_event.status
        if status == NOTE_ON and midi_event.velocity == 0:
            status = NOTE_OFF
        try:
            if self.process_map[status]( midi_event ):
                # Note has been found.
                return
        except KeyError:
            # No process for this type of event.
            pass
        # Do not pass through note on/note off events that triggered a note.
        if self.passthrough:
            self.passthrough(midi_event)
        elif status == NOTE_ON:
            ActuatorStats.count("note not found")

    def notedef_on( self, midi_note ):
        return self._notedef_onoff( midi_note, 1 )

    def notedef_off( self, midi_note ):
        return self._notedef_onoff( midi_note, 0 )

    def _notedef_onoff( self, midi_note, onoff ): 
        # onoff: 0 for note off, 1 for note on, see order in self.define_note()
        actions = self._get_actions( midi_note )
        for act in actions:
            # act[0] is actuator.off()
            # act[1] is actuator.on()
            # act[2] is register
            # act[3] is the actuator (not used here, since the on/off methods are available)
            if act[2].value():
                # This calls the on() or off() method of the appropriate driver/actuator
                act[onoff]()
        # Return True to caller if a note was played. 
        # This is used here for passthrough and in organtuner.py
        # to skip notes that are not present while playing scales.
        return bool(actions)          

    def _note_event_on( self, midi_event ):
        return self._note_event( midi_event, 1 )

    def _note_event_off( self, midi_event ):
        return self._note_event( midi_event, 0 )

    def _note_event( self, midi_event, onoff ):
        CURRENT_NOTE.program_number = self.channelmap1[midi_event.channel]
        CURRENT_NOTE.midi_number = midi_event.note
        return self._notedef_onoff( CURRENT_NOTE, onoff )

    def _program_change( self, midi_event ):
        if midi_event.channel != DRUM_CHANNEL:
            self.channelmap1[midi_event.channel] = midi_event.program
        
        # Pass through all program change events, even if processed.
        # (i.e. surplus program changes won't hurt on passthrough)
        return False
 
    def processd0( self, midi_event ):
        # Process compress_midi.py -d0 events.
        CURRENT_NOTE.program_number = self.channelmap1[midi_event.channel]
        value = midi_event.value
        if value <= 63: # 0 <= value <= 63
            CURRENT_NOTE.midi_number = value+40
            self._notedef_onoff( CURRENT_NOTE, 0 )
        else:
            CURRENT_NOTE.midi_number = value-24 # value-64+40
            self._notedef_onoff( CURRENT_NOTE, 1 )
        # Never use this type of 0xd0 events in passthrough.
        return True
     
    def must_process( self, midi_event ):
        return (
            midi_event.status in self.process_map or
            (self.passthrough and midi_event.is_channel()) 
            )

    def all_notes_off( self ):
        self.actuator_bank.all_notes_off( )

    async def play_random_note(self, duration_msec):
        if not hasattr( self, "all_midis" ):
            # Cache a list of all MIDI notes for future use in self.play_random_note()
            self.all_midis = [ 
                midi_note for midi_note in self.notedict.keys() 
                if midi_note.program_number != DRUM_PROGRAM ]
        try:
            midi_note = choice( self.all_midis )
            self.notedef_on( midi_note )
            await asyncio.sleep_ms(duration_msec)
            self.notedef_off( midi_note )
            await asyncio.sleep_ms(100)
        except IndexError:
            pass # list is empty

    async def clap(self, n):
        # Used at start up to make some noise to say that system is up.
        for _ in range(n):
            await self.play_random_note(50)

    def get_notedict(self):
        # Used by webserver to list pinout
        return self.notedict

    def _all_off_for_register( self, register_name ):
        # Turn off all notes for a given register. 
        # This is used when a register is turned off, to turn off
        # all actuators related to this register.
        # This takes about 1 or 2 msec, plus time to force_off,
        # so no much gain if optimized
        for actions in self.notedict.values():
           for actuator, register, _ in actions:
                if register.name == register_name:
                    # Turn off even if there is pending note off count...
                    actuator.force_off()
