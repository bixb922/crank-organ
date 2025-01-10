# (c) 2023 Hermann Paul von Borries
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
WILDCARD_PROGRAM = 0 # Must be zero, see basic_note_on/basic_note_off

tuning_frequency = 440

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
            instr = f"P{self.program_number}-"

        return f"{instr}{self.note_name()}({self.midi_number})"
    
    def __repr__(self):
        return str(self)

    def frequency(self):
        return tuning_frequency * 2 ** ((self.midi_number - 69) / 12)

    def set_tuning_frequency( self, new_frequency ):
        global tuning_frequency
        tuning_frequency = new_frequency
        
    def cents(self, measured_freq):
        # Cents difference between the measured frequency and the nominal frequency
        if not measured_freq or measured_freq <= 0:
            return None
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