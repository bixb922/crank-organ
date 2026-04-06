# (c) Copyright 2025 Hermann Paul von Borries. All rights reserved.
# MIT License

# This scripts needs: 
#   pip install mido 
# as prerrequisite
import os
import zlib
import sys
import json
import argparse
from pathlib import Path
import unicodedata
import mido
from datetime import datetime, timedelta
import hashlib, binascii
import sys

STORED_SETLIST_NUMBER = 9
STORE_WEEKS = 4

this_file_py = Path(__file__).name
this_file = Path(__file__).stem
this_file_json = this_file + ".json"

DESC = """<this_file>.py
Compresses each .MID or .mid file in the input folder, writing the compressed file to the output folder. 
Strips all meta MIDI messages, and most channel messages leaving only note on, note off and program change. 
Incorporates all set_tempo indications in the output. 
Optimizes the MIDI file for the crank organ software, then compresses with gzip, adding a .gz to the file name.
Only compresses files newer than the compressed output file (can be overridden with -f)
Shows some approximate statistics about the compression when finished.
Format is:
python <this_file>.py <input folder> <output folder>
Input and output folder need only be specified once. From then on, they
are stored in <this_file>.json in the current folder.
Can also compare with a tunelib.json copied from the microcontroller to the PC, to see difference between local and microcontroller's tunelib folder.
All MIDI output files are generated with 96 ticks per beat, which was used in the past,
and is a good compromise between file size and timing resolution.
"""
def parse_arguments():
    parser = argparse.ArgumentParser(
            "python " + this_file_py,
            description=DESC.replace("<this_file>", this_file),
            formatter_class = argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folders', 
                    type=str, 
                    nargs="*",
                    help='Input and output folder path')

    parser.add_argument("--d0", "-d0",
                    dest="status_d0", 
                    action=argparse.BooleanOptionalAction,
                    help="Use status D0 wherever possible" )

    #parser.add_argument("--tunelib", "-t",
    #                dest="tunelib",
    #                type=str,
    #                default=None,
    #                help="tunelib.json file to compare with microcontroller info")
    
    parser.add_argument( "--known-programs", "-k",
                        dest="known_programs", 
                        type=int,
                        nargs="+",
                        help="Know midi program numbers. First program number is used to replace any program numbers of midi file not in this list (catch all program).")
    
    args = parser.parse_args()
    if len(args.folders) >= 3:
        print("Can only specify two folders, the input and the output folder")
        sys.exit(1)

    try:
        with open(this_file_json) as file:
            j = json.load(file)
    except FileNotFoundError:
        if len(args.folders) != 2:
            print(f"No {this_file_json} found, must specify input and output folder. Use --help to get command description")
            sys.exit()
        j = {}
    json_changed = False
    if args.folders:
        if len(args.folders) >= 1:
            j["input_folder"] = args.folders[0]
            json_changed = True
        if len(args.folders) >= 2:
            j["output_folder"] = args.folders[1]
        json_changed = True
    #if args.tunelib:
    #    j["tunelib"] = args.tunelib
    #    json_changed = True

    if args.known_programs:
        j["known_programs"] = args.known_programs
        if set(args.known_programs)-set(range(1,129)):
            print("Known program numbers must be between 1-128.")
            sys.exit(1)
        if len(args.known_programs) >= 15:
            print("Too many known programs, maximum is 15")
            sys.exit(1)
        if len(args.known_programs) == 0:
            print("At least one known program number must be specified")
        json_changed = True
    
    if args.status_d0 is not None:
        j["status_d0"] = args.status_d0
        json_changed = True
    if j["status_d0"]:
        print("D0 MIDI compression")

    if json_changed:
        with open(this_file_json, "w") as file:
            json.dump( j, file )


    return j["input_folder"], j["output_folder"], j.get("bass_correction",{}),j.get("known_programs", [1]), j.get("status_d0",False)

def zlib_compress( original_data ):
                                                                                                          
    # This will create the zlib header (8 bytes) that contains level and wbits for deflate
    # MicroPython apparently has some problems with wbits=14?
    # Use best compression. (Python gzip does not have wbits=)
    zco = zlib.compressobj( level=9, wbits=13 )
    compressed_data = zco.compress( original_data )
    compressed_data += zco.flush()
    return compressed_data
                                                                                                          
def zlib_decompress( filename ):
    data = read_file( filename )
    return zlib.decompress( data )
    
def file_info( filename ):
    try:
        stat = os.stat(filename)
        return stat.st_size, stat.st_mtime
    except FileNotFoundError:
        return -1, -1
    
def size_on_flash( size ):
    # Return the estimated file size considering that the file will be stored on flash
    # in blocks of 4096 bytes.
    # If the file is smaller than 4096 bytes, return 1 block.
    # MIDI files smaller than the littlefs2 limit of 512 bytes are not common.
    # Also: this does not add the overhead for the inode (filename, etc)    
    return min((size+4095)//4096,4096)

def read_file( filename ):
    with open(filename, "rb") as file:
        return file.read()
    
def write_file( filename, data ):
    with open(filename, "wb") as file: # type:ignore
        file.write(data)

class Event:
    # Container for simplified note on/off events.
    def __init__( self, time, event_type, channel, program1, note ):
        self.type = event_type
        self.channel = channel
        self.note = note
        self.time = time
        self.program1 = program1
        if self.program1 is not None and self.note is not None:
            self.key = program1*256 + self.note # a unique key to compare notes

    def set_program1( self, program1 ):
        self.program1 = program1
        self.key = program1*256 + self.note # a unique key to compare notes

def sort_event_list( event_list ):
    translate = {
        "program_change":0,
        "note_on":1,
        "note_off":2,
    }
    # Time being equal sort note on before note off
    event_list.sort( key=lambda ev: f"{ev.time:09.3f}_{translate[ev.type]}" )
    return event_list

def statistics( s, event_list ):
    # duration = max(ev.time for ev in event_list)
    # note_on_count = sum(1 for ev in event_list if ev.type == "note_on")
    # note_off_count = sum(1 for ev in event_list if ev.type == "note_off")
    # print(f"    {s} event stats count={len(event_list)} {duration=:.3f} {note_on_count=} {note_off_count=}")
    return 

def read_midi( filename ):
    midifile = mido.MidiFile( filename )
    print(f"    MIDI file read, {len(midifile.tracks)} tracks, {midifile.ticks_per_beat} ticks per beat")
    event_list = []
    running_time = 0
    for mido_event in midifile:
        running_time += mido_event.time
        if mido_event.type == "note_on" or mido_event.type == "note_off":
            ev = Event( running_time, "note_off", mido_event.channel, None, mido_event.note)
            if mido_event.type == "note_on" and mido_event.velocity > 0:
                ev.type = "note_on"
            event_list.append( ev )
        elif mido_event.type == "program_change":
            ev = Event( running_time, "program_change", mido_event.channel, mido_event.program+1, None)
            event_list.append( ev )
    # Don't solve program changes here, first sort!
    return sort_event_list( event_list )

def solve_program_changes( event_list, known_programs ):
    channelmap1 = [1]*16
    channelmap1[9] = 129
    programs = set( ev.program1 for ev in event_list )
    if 129 in programs:
        known_programs.append( 129 )
    for ev in event_list:
        if ev.type == "note_on" or ev.type == "note_off":
            ev.set_program1(channelmap1[ev.channel] )
        elif ev.type == "program_change":
            program1 = ev.program1
            if program1 not in known_programs:
                program1 = known_programs[0]
            channelmap1[ev.channel] = program1
    return event_list

def  apply_bass_correction( event_list, bass_correction ):
    # Calculate running time and apply bass correction

    if bass_correction:
        print("    Applying bass correction", bass_correction )
    
    max_correction = max( bass_correction.values(), default=0 )
    for event in event_list:
        correction = max_correction
        if event.type == "note_on":
            if event.channel != 9:
                correction -= bass_correction.get( str(event.note), 0 )
            else:
                correction -= bass_correction.get( "drum" + str(event.note), 0 )
        # Keep only these events. 
        if event.type == "note_on" or event.type == "note_off":
            event.time = event.time + correction
    # Sort by time. If time is equal to 1 msec, then note_on is before note_off
    # If not the continuity may be affected
    return sort_event_list( event_list )

def pair_note_on_off( event_list ):
    currently_on = {}
    output_list = []
    for event in event_list:
        if event.type == "note_on":
            cn = currently_on.setdefault( event.key, {"count":0, "start_time": event.time, "program1": event.program1, "note":event.note } )
            cn["count"] += 1
        elif event.type == "note_off" or ( event.type == "note_on" and event.velocity == 0):
            if event.key in currently_on:
                cn = currently_on[ event.key ]
                cn["count"] -= 1
                if cn["count"] <= 0:
                    # Don'r include very, very short notes
                    if event.time-cn["start_time"] >= 0.01:
                        note_on = Event(  cn["start_time"], "note_on",  event.channel, event.program1, event.note )
                        note_off = Event(  event.time,      "note_off", event.channel, event.program1, event.note )
                        output_list.append( note_on )
                        output_list.append( note_off )
                    del currently_on[event.key]

        #if event.time > 60 and event.note == 60:
        #    s = ""
        #    for k, cn in currently_on.items():
        #        p = k//256 
        #        n = k&255
        #        s += f" {p}.{n}"
        #    print(f"    pair {event.time:.3f} {event.type:8s} {event.program1=} {event.note=} {s}" )
  
    for key, cn in currently_on.items():
        if cn["count"] > 0:
            note = key % 256
            program1 = key // 256
            print(f"Note left on since {cn["start_time"]:.3f} to {event.time:.3f} {program1=} {note=}")
            note_on = Event(  cn["start_time"], "note_on",  event.channel, event.program1, event.note )
            note_off = Event(  event.time,      "note_off", event.channel, event.program1, event.note )
            output_list.append( note_on )
            output_list.append( note_off )
    if currently_on:
        print("???Error stop processing, notes left on")
        sys.exit()

    return sort_event_list( output_list )

def write_midi_file( event_list, output_filename, status_d0 ):
    # Use a high value for ticks_per_beat, if not bass correction does not work
    # Compression could be better with a lower value....
    tempo = 500_000
    ticks_per_beat = 96 # better not use lower values!
    tempo_secs = tempo/1_000_000
 
    midifile = mido.MidiFile()
    midifile.ticks_per_beat = ticks_per_beat
    
    trackdict = {} # translates program number (1-128, 129) to MIDO track
    trackchannel = {} # translates program number to channel number
    tracktime = {} # keeps MIDI time for each track
    eventcount = {} # statistics, output events per track

    available_channels = list(range(16))
    available_channels.pop(9) # channel 10 is not available for non-drum program numbers
   
    drum_program = 129
    programs = set( ev.program1 for ev in event_list )
    # Create tracks and fill in data structures
    for program1 in programs:
        track = mido.MidiTrack()
        trackdict[program1] = track
        if program1 == drum_program:
            # Drum program 129 goes to MIDI channel 10
            channel = 9
            trackchannel[program1] = channel
            # No program change for drum channel
        else:
            channel = available_channels.pop(0) # assign next available channel
            trackchannel[program1] = channel
            track.append( mido.Message( "program_change", program=program1-1, channel=channel, time=0))
        tracktime[program1] = 0
        eventcount[program1] = 0
        midifile.tracks.append( track )
     

    # Append the events to the tracks according to their channel.
    for event in event_list:
        if event.type == "note_on" or event.type == "note_off":
            program1 = event.program1
            track = trackdict[program1]
            channel = trackchannel[program1]
            last_time = tracktime[program1]

            # Now calculate the MIDI file delta time.
            # Due to integer vs floating point precision, delta could be -1 or -2
            # sometimes, so do a max(delta,0)
            delta = max(round((event.time-last_time)/tempo_secs*ticks_per_beat),0)
            if 40 <= event.note <= 103 and status_d0:
                n = event.note-40
                if event.type == "note_on":
                    n += 64
                track.append( mido.Message( "aftertouch", value=n, time=delta, channel=channel))
            else:
                velocity = 0
                if event.type == "note_on":
                    velocity = 64
                track.append( mido.Message( "note_on", note=event.note, velocity=velocity, time=delta, channel=channel ) )
            # Can't simply do tracktime[channel] = start_time
            # Must do the calculation using the MIDI delta, 
            # if not rounding/truncating errors
            # will start to propagate getting significant at the end
            # of tunes.
            tracktime[program1] += delta * tempo_secs / ticks_per_beat
            # No need to output further "set tempo" meta events since event.time
            # already reflects the tempo changes
            eventcount[program1]+=1
    midifile.save( output_filename )

def reformat_midi( input_filename, output_filename, bass_correction, known_programs, status_d0 ):
    # Get rid of all messages in the file except note on, note off and program_change.
    # MIDO will have preprocessed all set tempo, so we don't need keep them.
    # Convert all note off messages to note on with velocity 0,
    # because running status will compress the raw midi file better.
    # Use fixed velocity for note on, this will optimize gzip compression.
    # Insert a program change to flute for each channel (except drum channel)
    # Assign one channel to each midi file track, to optimize running status.
    # Insert one set tempo with a standard tempo, since the
    # timing is already taken care of.

    # Read the midi file
    event_list = read_midi( input_filename )
    statistics("read_midi", event_list)

    event_list = solve_program_changes( event_list, known_programs )

    event_list = apply_bass_correction( event_list, bass_correction )
    statistics("bass correction", event_list)

    event_list = pair_note_on_off( event_list )
    statistics("pair notes", event_list)
 

    write_midi_file( event_list, output_filename, status_d0 )



input_filelist = []

def compress_midi_file( input_folder, filename, output_folder, bass_correction, known_programs, status_d0 ):
    pf = Path( filename )
    input_filename = Path(input_folder) / pf
    output_filename = (Path(output_folder) / pf).with_suffix( pf.suffix + ".gz")
    input_size, input_date = file_info(input_filename)
    output_size, output_date = file_info(output_filename)
    input_filelist.append( (filename, input_size, input_date) )
    if input_date >= output_date:
        print("Input file", filename, "processing...")
        print("    input", input_size, "bytes")
        reformat_midi( input_filename, "temp.mid", bass_correction, known_programs, status_d0 )
        
        data = read_file( "temp.mid" )
        decompressed_size = len(data)
        print("    intermediate midi file", decompressed_size, "bytes")
        
        compressed = zlib_compress( data )
        write_file( output_filename, compressed )
        output_size = len(compressed)
        print("    output .gz written", output_size, "bytes")

    else:
        decompressed_size = len(zlib_decompress( output_filename ))
    return input_size, decompressed_size, output_size

def remove_deleted_files( input_folder, output_folder ):
    input_files =  set( ( fn+".gz" for fn in os.listdir( input_folder ) if fn.lower().endswith(".mid")) )
    output_files = set ( fn for fn in os.listdir(output_folder) if fn.lower().endswith(".mid.gz") )
    for filename in output_files - input_files:
        os.remove( Path(output_folder) / filename )
        print(f"Deleting file {filename}, source (uncompressed) file not found")

# def compare_folder_with_tunelib( folder, tunelib_file ):
#     def compare( set1, set2 ):
#         nt = []
#         for fn in set1-set2:
#             nt.append(fn)
#         nt.sort()
#         for fn in nt:
#             print("    ", fn)
#     def nfc( s ):
#         return unicodedata.normalize( "NFC", s )
    
#     TLCOL_FILENAME = 6
#     # TLCOL_SIZE = 11
#     if not tunelib_file:
#         return

#     with open(tunelib_file,encoding="utf8") as file:
#         tunelib = json.load( file )
        
#     tunelib_files = set( nfc(tune[TLCOL_FILENAME]) for tune in tunelib.values())
#     folder_files = set( nfc(fn) for fn in os.listdir(folder) if fn.lower().endswith(".mid") or fn.lower().endswith(".mid.gz") )
#     print("In tunelib (microcontroller) but not in folder")
#     compare( tunelib_files, folder_files )
#     print("In folder but not in tunelib (microcontroller)")
#     compare( folder_files, tunelib_files )

def make_setlist_newest( output_folder, input_filelist ):
    def _compute_hash(filename):
        filename = unicodedata.normalize("NFKC", filename )

        # Each tune has a unique hash derived from the filename
        # This is the tuneid. By design it is made unique (see _make_unique_hash)
        # and stable.
        if filename.endswith(".gz"):
            filename = filename[:-3]
        digest = hashlib.sha256(filename.encode("utf-8")).digest()
        folded_digest = bytearray(6)
        i = 0
        for n in digest:
            folded_digest[i] ^= n
            i = (i + 1) % len(folded_digest)
        hash = binascii.b2a_base64(folded_digest).decode()
        # Make result compatible with URL encoding
        return hash.replace("\n", "").replace("+", "-").replace("/", "_")

    input_filelist.sort( key=lambda x:x[2], reverse=True )
    weeks = datetime.now() - timedelta(weeks=STORE_WEEKS)
    i = 0
    setlist = []
    for i, (filename, file_size, mtime ) in enumerate(input_filelist):
        modified = datetime.fromtimestamp(mtime)
        if modified >= weeks:
            setlist.append( "i" + _compute_hash(filename) )
        i += 1
    setlist_name = f"setlist_stored_{STORED_SETLIST_NUMBER}.json"
    print(f'{len(setlist)} files now in "recent additions" setlist file {setlist_name} on PC')
    with open(output_folder + "/" + setlist_name,"w") as file:
        json.dump( setlist, file )
    print(f"Setlist for modified in last {STORE_WEEKS} weeks written to", setlist_name, " folder=", output_folder)


def main():
    input_folder, output_folder, bass_correction, known_programs, status_d0 = parse_arguments()
    print(f"Input folder", input_folder)
    print(f"Output folder", output_folder)
    #if tunelib_file:
    #    print(f"Tunelib file", tunelib_file )
    #    compare_folder_with_tunelib( output_folder, tunelib_file )

    input_blocks = 0
    output_blocks = 0
    input_bytes = 0
    output_bytes = 0
    decompressed_bytes = 0
    n = 0
    max_decompressed_size = 0
    for filename in os.listdir( input_folder ):
        if filename.lower().endswith(".mid"):

            input_size, decompressed_size, output_size = compress_midi_file(
                input_folder, 
                filename, 
                output_folder,  
                bass_correction,
                known_programs,
                 status_d0 )
            
            max_decompressed_size = max(max_decompressed_size, decompressed_size)
            input_blocks += size_on_flash(input_size)
            output_blocks += size_on_flash(output_size)
            input_bytes += input_size
            output_bytes += output_size
            decompressed_bytes += decompressed_size
            n += 1
    remove_deleted_files( input_folder, output_folder )

    if n == 0:
        # No files, no statistics
        return
    
    # Store setlist with newest files
    # global input_filelist was already populated by compress_midi_file
    make_setlist_newest( output_folder, input_filelist )

    # Print statistics
    #print(f"Maximum decompressed size={max_decompressed_size} bytes")
    avg_output = output_blocks/n
    avg_input = input_blocks/n
    ratio = output_blocks/input_blocks
    midi_ratio = decompressed_bytes/input_bytes
    print(f"{n} files {input_blocks=} {output_blocks=} (1 block=4096 bytes)")
    print(f"average input={avg_input:4.1f} blocks/file, average output={avg_output:4.1f} blocks/file, block compression {ratio=:4.2f}")
    print(f"average input={input_bytes/n/1000:4.1f} kbytes/file, average output={output_bytes/n/1000:4.1f} kbytes/file, bytes midi reduction ratio={midi_ratio:4.1f}, bytes compression ratio={output_bytes/input_bytes:4.2f}")
	# As of Dic 2024: overhead is 634 blocks, 512 for Micropython
	# rest for /data, /lib y /software
    # blocks approx including micropython, *.mpy, static, data (with compiled mpy files and compressed static files)
    # and data files, 4 error.log files, a tunelib.json and lyrics.json
    # with 2 backups each, estimated size.
    # If static is compressed and micropython is compiled:
    application_overhead = 720
    # If static is not compressed and micropython is not compiled
    application_overhead = 840
    print("Estimated capacities based on current average MIDI file size, no lyrics:")
    for flash_size in (8, 16):
        blocks = flash_size*1024*1024/4096
        blocks_free = blocks - application_overhead
        #print(f"{flash_size=} {blocks=} {blocks_free=}")
        input_capacity = round(blocks_free/avg_input)
        output_capacity = round(blocks_free/avg_output)
        model = f"N{flash_size}R8"
        print(f"{model:5s}: raw capacity={input_capacity:4.0f}, compressed capacity={output_capacity:4.0f} midi files")

        
main()
    
# Decompressing a MIDI file to flash takes somewhere between 200 ms and 800ms
# on the ESP32-S3. Could be faster if decompressed to RAM on the fly
# but that raises the garbage collection time...

# N16R8 os.statvfs("") with empty file system:
#  os.statvfs("")
# (4096, 4096, 3584, 3582, 3582, 0, 0, 0, 0, 255)
# means that overhead for micropython = 512 blocks = 2MB

# May 2025, with installed /software, /data, /lib but empty tunelib:
# (4096, 4096, 3584, 3438, 3438, 0, 0, 0, 0, 255)
# about 600.000 bytes (144 blocks)

# Effect of quantization (ticks per beat) on compression
# Quantize=10.0 ticks_per_beat=50
#434 files input_blocks=1884 output_blocks=750 (1 block=4096 bytes)
#average input= 4.3 blocks/file, average output= 1.7 blocks/file, block compression ratio=0.40
#average input=  16 kbytes/file, average output=   5 kbytes/file, bytes compression ratio=0.32
#Estimated capacities based on current average MIDI file size, no lyrics:
#N8R8 : raw capacity= 278, compressed capacity= 699 midi files
#N16R8: raw capacity= 750, compressed capacity=1884 midi files

# Quantize about 5, ticks_per_beat = 96
#434 files input_blocks=1884 output_blocks=785 (1 block=4096 bytes)
#average input= 4.3 blocks/file, average output= 1.8 blocks/file, block compression ratio=0.42
#average input=  16 kbytes/file, average output=   5 kbytes/file, bytes compression ratio=0.34
#Estimated capacities based on current average MIDI file size, no lyrics:
#N8R8 : raw capacity= 278, compressed capacity= 668 midi files
#N16R8: raw capacity= 750, compressed capacity=1800 midi files


# Quantize=3.0 ticks_per_beat=167
# 434 files input_blocks=1884 output_blocks=822 (1 block=4096 bytes)
# average input= 4.3 blocks/file, average output= 1.9 blocks/file, block compression ratio=0.44
# average input=  16 kbytes/file, average output=   6 kbytes/file, bytes compression ratio=0.36
# Estimated capacities based on current average MIDI file size, no lyrics:
# N8R8 : raw capacity= 278, compressed capacity= 638 midi files
# N16R8: raw capacity= 750, compressed capacity=1719 midi files

# As of June 2025, ticks_per_beat = 96
# 519 files input_blocks=2311 output_blocks=1003 (1 block=4096 bytes)
# average input= 4.5 blocks/file, average output= 1.9 blocks/file, block compression ratio=0.43
# average input=  16 kbytes/file, average output=   6 kbytes/file, bytes compression ratio=0.36
# Estimated capacities based on current average MIDI file size, no lyrics:
# N8R8 : raw capacity= 271, compressed capacity= 625 midi files
# N16R8: raw capacity= 731, compressed capacity=1685 midi files


# Feb 2026 with track reduction, ticks_per_beat=96
# 681 files input_blocks=3013 output_blocks=1270 (1 block=4096 bytes)
# average input= 4.4 blocks/file, average output= 1.9 blocks/file, block compression ratio=0.42
# average input=16.0 kbytes/file, average output= 5.6 kbytes/file, bytes compression ratio=0.35
# Estimated capacities based on current average MIDI file size, no lyrics:
# N8R8 : raw capacity= 273, compressed capacity= 648 midi files
# N16R8: raw capacity= 736, compressed capacity=1746 midi files

# Feb 2026 with track reduction and --d0, ticks_per_beat=96
# 681 files input_blocks=3013 output_blocks=1163 (1 block=4096 bytes)
# average input= 4.4 blocks/file, average output= 1.7 blocks/file, block compression ratio=0.39
# average input=16.0 kbytes/file, average output= 4.9 kbytes/file, bytes compression ratio=0.31
# Estimated capacities based on current average MIDI file size, no lyrics:
# N8R8 : raw capacity= 273, compressed capacity= 707 midi files
# N16R8: raw capacity= 736, compressed capacity=1907 midi files

# With lower ticks per beat=50 capacity increases a bit
# 681 files input_blocks=3013 output_blocks=1105 (1 block=4096 bytes)
# average input= 4.4 blocks/file, average output= 1.6 blocks/file, block compression ratio=0.37
# average input=16.0 kbytes/file, average output= 4.5 kbytes/file, midi reduction ratio= 0.5, bytes compression ratio=0.28
# Estimated capacities based on current average MIDI file size, no lyrics:
# N8R8 : raw capacity= 273, compressed capacity= 744 midi files
# N16R8: raw capacity= 736, compressed capacity=2007 midi files