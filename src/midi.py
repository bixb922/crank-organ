# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# MIDI support:
# This module contains the NoteDef (note definition) class, 
# which is used to store note definitions
# done on the pinout.html page and parsed by pinout.py.
# "Real" MIDI notes that are retrieved from MIDI files 
# are never instantiated as NoteDef 
# but as program number/midi note number

from math import log

# Some useful functions related to MIDI
_NOTE_LIST = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")

# Define the MIDI channel number for drums (set by GM standard)
DRUM_CHANNEL = 9 # MIDI channel 10 (physical=9)

# Definitions for NoteDef
DRUM_PROGRAM = 129
WILDCARD_PROGRAM = 0 # Matches all programs


class NoteDef:
    tuning_frequency = 440

    # Note definition: this class is used to store note definitions
    # done on the pinout.html page and parsed by pinout.py.
    # Also, a parsed MIDI note is represented as NoteDef with a 
    # program number != WILDCARD_PROGRAM, but program_number
    # may be DRUM_PROGRAM for drum notes.
    def __init__(self, program_number, midi_number):
        # Instrument can be:
        #   DRUM_PROGRAM (129) for drum channel 10, or
        #   WILDCARD_PROGRAM (0), or
        #   any MIDI program number from 1-128 (not 0-127!!!!)
        # If program_number is None, then it means: WILDCARD_PROGRAM
        #
        # midi_number can be 0-127 or None.
        # If midi_number is None, then this note is undefined (this
        # happens only if midi number field is left blank on the user interface)
        self.set( program_number, midi_number )
        # self.program_number and self.midi_number are accessed as if
        # they were properties, no @property (it's faster, less code)

    @classmethod
    def set_tuning_frequency( cls, new_freq ):
        if new_freq:
            NoteDef.tuning_frequency = new_freq    
        else:
            from drehorgel import config
            NoteDef.tuning_frequency = config.tuning_frequency

    def set( self, program_number, midi_number ):
         # If program_number is None, set to WILDCARD_PROGRAM
        self.program_number = program_number or WILDCARD_PROGRAM
        self.midi_number = midi_number

    def __str__(self):
        if self.midi_number is None:
            return ""
        
        if self.program_number == WILDCARD_PROGRAM:
            instr = "*-"
        elif self.program_number == DRUM_PROGRAM:
            instr = f"Dr{self.program_number}-"
        else:
            instr = f"P{self.program_number}-"

        return f"{instr}{self.note_name()}({self.midi_number})"
    
    def __repr__(self):
        return str(self)

    def frequency(self):
        return NoteDef.tuning_frequency * 2 ** ((self.midi_number - 69) / 12)

    def cents(self, measured_freq):
        # Cents difference between the measured frequency and the nominal frequency
        if not measured_freq or measured_freq <= 0:
            return None
        # self.frequency() already considers midi.tuning_frequency
        return 1200 * log(measured_freq / self.frequency()) / log(2)

    def note_name(self):
        # e.g. Db4 or C4.
        if not self.is_valid():
            return ""
        if self.program_number == DRUM_PROGRAM:
            return str(self.midi_number)
        return _NOTE_LIST[self.midi_number % 12] + str((self.midi_number // 12) - 1)

    def is_valid( self ):
        return self.midi_number is not None
    
    # A correct note has midi number between 0 and 127
    # and program number between 0 and 129
    def is_correct( self ):
        return (self.is_valid() and 0 <= self.midi_number <= 127 
                and WILDCARD_PROGRAM <= self.program_number <= DRUM_PROGRAM)

    def __bool__( self ):
        # Both 0 means "no midi note"
        # midi_number has to be neither None nor 0
        return self.midi_number or self.program_number != 0
    
    # controller.notedict uses NoteDef as key
    # Two NoteDef are equal if both program_number and midi_number are equal
    # Define __hash__ and __eq__ accordingly.
    def __hash__( self ):
        return self.program_number*256 + self.midi_number
    
    def __eq__( self, other ):
        return self.program_number == other.program_number and self.midi_number == other.midi_number
    
    def wildcard( self  ):
        # Avoid allocating another NoteDef for each midi note
        # And the result of wildcard() is never stored, only used as argument of a dict.get()
        wildcard_note.midi_number = self.midi_number # should use .set()
        return wildcard_note
    
wildcard_note = NoteDef( WILDCARD_PROGRAM, 0 ) # allocate once
