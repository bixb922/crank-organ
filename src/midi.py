# (c) 2023 Hermann Paul von Borries
# MIT License
# MIDI note class and MIDIdict.
# The MIDI note class and MIDIdict allow MIDI notes with a "any" program number
# That eases the configuration for simple crank organs, but allows
# sophisticated configuration of MIDI notes addressable with program numbers
# and percussion (drums) channel support.
# MIDIdict is a dictionary that allows search efficiently for a MIDI Note.

# Also included: some functions to get note names, frequency, cents

from collections import OrderedDict
from math import log

# Some useful functions related to MIDI
_NOTE_LIST = ( "C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B" )



def frequency_to_midi( freq ):
    # Find which organ note corresponds to this frequency
    for midi in pinout.all_valid_midis:
        f = midi_to_frequency( midi )
        if f*2**(0.5/12) < freq <= f*2**(1.5/12):
            return midi
    return None

def find( all_valid_midis, midi_note_number ):
    for a in all_valid_midis:
        if (a.midi_note == midi_note_number and
           a.instrument != "z"):
                return a
    raise KeyError

DRUM_PROGRAM = 129
    
GM_PROGRAM=[
"",
"Acoustic Grand Piano",
"Bright Acoustic Piano",
"Electric Grand Piano",
"Honky-tonk Piano",
"Electric Piano 1",
"Electric Piano 2",
"Harpsichord",
"Clavi",
"Celesta",
"Glockenspiel",
"Music Box",
"Vibraphone",
"Marimba",
"Xylophone",
"Tubular Bells",
"Dulcimer",
"Drawbar Organ",
"Percussive Organ",
"Rock Organ",
"Church Organ",
"Reed Organ",
"Accordion",
"Harmonica",
"Tango Accordion",
"Acoustic Guitar (nylon)",
"Acoustic Guitar (steel)",
"Electric Guitar (jazz)",
"Electric Guitar (clean)",
"Electric Guitar (muted)",
"Overdriven Guitar",
"Distortion Guitar",
"Guitar Harmonics",
"Acoustic Bass",
"Electric Bass (finger)",
"Electric Bass (pick)",
"Fretless Bass",
"Slap Bass 1",
"Slap Bass 2",
"Synth Bass 1",
"Synth Bass 2",
"Violin",
"Viola",
"Cello",
"Contrabass",
"Tremolo Strings",
"Pizzicato Strings",
"Orchestral Harp",
"Timpani",
"String Ensemble 1",
"String Ensemble 2",
"Synth Strings 1",
"Synth Strings 2",
"Choir Aahs",
"Voice Oohs",
"Synth Voice",
"Orchestra Hit",
"Trumpet",
"Trombone",
"Tuba",
"Muted Trumpet",
"French Horn",
"Brass Section",
"Synth Brass 1",
"Synth Brass 2",
"Soprano Sax",
"Alto Sax",
"Tenor Sax",
"Baritone Sax",
"Oboe",
"English Horn",
"Bassoon",
"Clarinet",
"Piccolo",
"Flute",
"Recorder",
"Pan Flute",
"Blown bottle",
"Shakuhachi",
"Whistle",
"Ocarina",
"Lead 1 (square",
"Lead 2 (sawtooth)",
"Lead 3 (calliope)",
"Lead 4 (chiff)",
"Lead 5 (charang)",
"Lead 6 (voice)",
"Lead 7 (fifths)",
"Lead 8 (bass + lead)",
"Pad 1 (new age)",
"Pad 2 (warm)",
"Pad 3 (polysynth)",
"Pad 4 (choir)",
"Pad 5 (bowed)",
"Pad 6 (metallic)",
"Pad 7 (halo)",
"Pad 8 (sweep)",
"FX 1 (rain)",
"FX 2 (soundtrack)",
"FX 3 (crystal=",
"FX 4 (atmosphere)",
"FX 5 (brightness)",
"FX 6 (goblins)",
"FX 7 (echoes)",
"FX 8 (sci-fi)",
"Sitar",
"Banjo",
"Shamisen",
"Koto",
"Kalimba",
"Bag pipe",
"Fiddle",
"Shanai",
"Tinkle Bell",
"Agogô",
"Steel Drums",
"Woodblock",
"Taiko Drum",
"Melodic Tom",
"Synth Drum",
"Reverse Cymbal",
"Guitar Fret Noise",
"Breath Noise",
"Seashore",
"Bird Tweet",
"Telephone Ring",
"Helicopter",
"Applause",
"Gunshot",
"drum"
]

class Note:
    def __init__( self, instrument=None, midi_note=None, byhash=None ):
        # Instrument can be:
        #   program number 1-128 (not 0-127!!!!)
        #   129 for drum channel 10/11
        #   0 or "" = wildcard to match any MIDI program number but not DRUM_PROGRAM, since the
        # percussion channel has to make exact match.
        # If created byhash=, then byhash is the hash of a midi.Note
        # and __init__ computes midi_note and instrument with this input
        if byhash is not None:
            self.midi_note = byhash % 256
            self.instrument = byhash // 256
            self.hash = byhash
        else:
            self.instrument = instrument
            self.midi_note = midi_note
            blank = ("", " ", "  ", "\xa0" )

            if self.instrument in blank:
                self.instrument = 0
            if self.midi_note in blank:
                self.midi_note = 0
            # Note(0,0) or Note("","") does not exist
            # and evaluates as False
            self.hash = self.instrument*256 + self.midi_note
     

        
    def __hash__( self ):  
        return self.hash
    
    def __str__( self ):
        if self.instrument == 0:
            instr = ""
        else:
            instr = f"{GM_PROGRAM[self.instrument]}({instr})-"
            
        note_name = f"{self.note_name()}({self.midi_note})"
        return f"{instr}{note_name}"
    
    def __repr__( self ):
        return str( self )
    
    def frequency( self ):
        return 440*2**((self.midi_note-69)/12)

    def cents( self, freq ):
        if freq <= 0:
            return None
        return 1200*log(freq/self.frequency())/log(2) 

    def note_name( self ):
        if self.instrument == DRUM_PROGRAM:
            return f"drum.{self.midi_note}"
        return  _NOTE_LIST[ self.midi_note%12 ] + str( (self.midi_note//12) - 1 )

    def __eq__( self, other ):
        
        # Same hash means same value:
        if self.hash == other.hash:
            
            return True
        # Now test for match with wildcard program name
        # Drum program does never match wildcard
        if self.instrument == DRUM_PROGRAM or other.instrument == DRUM_PROGRAM:
            return False
        # This is the wildcard match, needs to match
        # only midi note, not program number
        if not self.instrument:
            return self.midi_note == other.midi_note
        return False

    def __bool__( self ):
        # Return false for a undefined note
        return bool(self.midi_note)
    
class MIDIdict(OrderedDict):

    def __getitem__( self, instrument_note ):
        
        try:
            # First check for exact match
            return super().__getitem__( instrument_note )
        except:
            if instrument_note.instrument == DRUM_PROGRAM:
                # Drum only accepts exact match
                raise KeyError
            # Search for a wildcard match if the exact
            # match failed
            return super().__getitem__( 
                Note( 0, instrument_note.midi_note ) 
            )                         

    def __contains__( self, instrument_note ):
        try:
            self.__getitem__( instrument_note )
            return True
        except:
            return False    


if __name__ == "__main__":

    d = MIDIdict()

    i0150 = Note( 1,50 )
    idd50 = Note( DRUM_PROGRAM,50 )
    i9950 = Note( 99, 50 )
    i9977 = Note( 99, 77 )
    
    print(f"i0150 {i0150}")
    print(f"idd50 {idd50}")
    print(f"i9950 {i9950}")
    print(f"i9977 {i9977}")


    d[i0150] = "i0150"
    assert i9950 not in d
    #print(i0150.hash)
    #print(d[i0150.hash])
    #1/0

    assert idd50 not in d
    assert i0150 in d
    assert d[i0150] == "i0150"
    assert idd50 not in d
    assert i9950 not in d
    assert i9977 not in d
    
    d[i0150] = "i0150"
    assert i0150 in d
    assert d[i0150] == "i0150"
    assert idd50 not in d
    assert i9950 not in d
    assert i9977 not in d

    d[idd50] = "idd50"
    assert i9950 not in d
    assert i0150 in d
    assert d[i0150] == "i0150"
    assert idd50 in d
    assert d[idd50] == "idd50"
    assert i9950 not in d
    assert i9977 not in d
    
    d[i9950] = "i9950"
    assert i0150 in d
    assert d[i0150] == "i0150"
    assert idd50 in d
    assert d[idd50] == "idd50"
    assert i9950 in d
    assert d[i9950] == "i9950"
    assert i9977 not in d
    
    d[i9977] = "i9977"
    assert i0150 in d
    assert d[i0150] == "i0150"
    assert idd50 in d
    assert d[idd50] == "idd50"
    assert i9950 in d
    assert d[i9950] == "i9950"
    assert i9977 in d
    assert d[i9977] == "i9977"
    
    assert Note(1,50) in d
    assert d[Note(1,50)] == "i0150"
    assert Note(DRUM_PROGRAM,50) in d
    assert d[Note(DRUM_PROGRAM,50)] == "idd50"
    assert Note(99,50) in d
    assert d[Note(99,50)] == "i9950"
    assert Note(99,77) in d
    assert d[Note(99,77)] == "i9977"
    
    d[Note("",50)] = "wildcard 50"
    assert i0150 in d
    assert d[i0150] == "i0150"
    assert idd50 in d
    assert d[idd50] == "idd50"
    assert i9950 in d
    assert d[i9950] == "i9950"
    assert i9977 in d
    assert d[i9977] == "i9977"
    assert Note("",50) in d
    assert d[Note("",50)] == "wildcard 50"
    d[Note("",44)] = "wildcard 44"
    assert Note(10,44) in d
    assert d[Note(10,44)] == "wildcard 44"
    assert Note(DRUM_PROGRAM,44) not in d
   
    assert Note("",50) in d
    assert d[Note("",50)] == "wildcard 50"
    assert Note(0,50) in d
    assert d[Note(0,50)] == "wildcard 50"
    assert Note(0,50) == Note("",50)

    
    h = Note("",50).hash
    nn = Note(byhash=h)
    assert nn.midi_note == 50
    assert nn.instrument == 0
    
    assert nn in d
    assert d[nn] == "wildcard 50"
    
    h = Note(10,50).hash
    assert Note(byhash=h) == Note(10,50)
    print("end of test")