
# This scripts needs: 
#   pip install mido 
# as prerrequisite
import os
import zlib
import sys
from collections import OrderedDict
import json
import argparse
from pathlib import Path
import unicodedata
import mido



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

    parser.add_argument("--force-compress", "-f",
                    dest="force_compress", 
                    default=False,
                    action=argparse.BooleanOptionalAction,
                    help="Force compression, disregarding file datetime" )
    
    parser.add_argument("--tunelib", "-t",
                    dest="tunelib",
                    type=str,
                    default=None,
                    help="tunelib.json file to compare with microcontroller info")
    
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
            sys.exit(1)
        j = {}
    json_changed = False
    if args.folders:
        if len(args.folders) >= 1:
            j["input_folder"] = args.folders[0]
            json_changed = True
        if len(args.folders) >= 2:
            j["output_folder"] = args.folders[1]
        json_changed = True
    if args.tunelib:
        j["tunelib"] = args.tunelib
        json_changed = True
    
    if json_changed:
        with open(this_file_json, "w") as file:
            json.dump( j, file )


    return j["input_folder"], j["output_folder"], args.force_compress, j.get("bass_correction",{}), j.get("tunelib")

def zlib_compress( original_data ):
                                                                                                          
    # This will create the zlib header (8 bytes) that contains level and wbits for deflate
    # MicroPython apparently has some problems with wbits=14?
    # Use best compression.
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

def read_midi( filename ):
    midifile = mido.MidiFile( filename )
    ticks_per_beat = midifile.ticks_per_beat
    event_list = [ event for event in midifile ]
    return event_list, ticks_per_beat

def reformat_midi( input_filename, output_filename, bass_correction ):
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
    event_list, ticks_per_beat = read_midi( input_filename )

    # Use a high value, if not bass correction does not work
    # Compression could be better with a lower value....
    # This combination makes 1 delta = 5 milliseconds
    # which should be enough and enables a good compression
    tempo = 500_000
    ticks_per_beat = 96
    tempo_secs = tempo/1_000_000
 

     # Calculate running time and apply bass correction
    running_time = 0

    if bass_correction:
        print("    Applying bass correction", bass_correction )
    
    max_correction = max( bass_correction.values(), default=0 )
    new_event_list = []
    for event in event_list:
        running_time += event.time
        correction = max_correction
        if event.type == "note_on" and event.velocity != 0:
            if event.channel != 9:
                correction -= bass_correction.get( str(event.note), 0 )
            else:
                correction -= bass_correction.get( "drum" + str(event.note), 0 )
        # Keep only these events. 
        if event.type == "note_on" or event.type == "note_off" or event.type == "program_change":
            new_event_list.append( [running_time+correction, event] )
    # Sort by running time
    event_list = None
    new_event_list.sort( key=lambda x: x[0] )

    midifile = mido.MidiFile()
    midifile.ticks_per_beat = ticks_per_beat
    
    trackdict = {}
    tracktime = {}
    # Make a track dictionary with one track per channel
    # There is no need for a "track 0" since no set tempo nor other meta
    # messages are needed. 
    # Append the tracks to the MIDI file.
    # First a track for channel 0, then one for each channel.
    track0 =  mido.MidiTrack()
    trackdict[0] = track0
    tracktime[0] = 0
    midifile.tracks.append( track0 )
    # Now repeat for other channels (if any)
    for channel in set( event.channel for _, event in new_event_list if event.channel != 0):
        track = mido.MidiTrack()
        trackdict[channel] = track
        tracktime[channel] = 0
        midifile.tracks.append( track )


    # Insert a set_tempo event at the beginning of the first track, 
    # (just to be sure)
    # with the standard tempo. Deltas will be adjusted to this tempo.
    track0.append( mido.MetaMessage( type="set_tempo", tempo=tempo, time=0))
    
    # Insert a initial program change for all  channels
    # to change sound to a type of flute. Can be overridden later by the input midi file.
    for channel, track in trackdict.items():
        if channel == 9:
            # Standard program for drum channel (channel 10)
            program = 0
        else:
            # A kind of flute for all other channels except drum
            program = 74
        track.append( mido.Message( type="program_change", program=program, time=0, channel=channel) )

    # Append the events to the tracks according to their channel.
    for start_time, event in new_event_list:
        
        if not hasattr(event,"channel"):
            raise RuntimeError("Event list has Meta/sysex event") 
            
        channel = event.channel
        
        # Get the MidiTrack and the time of the last event.
        # Should not happen that track_id is not in trackdict, but
        # if it does, use any track
        track = trackdict[channel]
        last_time = tracktime[channel]

        # Now calculate the MIDI file delta time.
        # Due to integer vs floating point precision, delta could be -1 or -2
        # sometimes, so do a max(delta,0)
        delta = max(round((start_time-last_time)/tempo_secs*ticks_per_beat),0)

        if event.type == "note_on" or event.type == "note_off":
            velocity = 0
            if event.type == "note_on" and event.velocity != 0:
                # Use a fixed velocity, this will optimize gzip compression
                velocity = 64
            # Use only Note On MIDI events, this will optimize the
            # running status and yield smallest file.
            track.append( mido.Message( "note_on", note=event.note, velocity=velocity, time=delta, channel=channel ) )
            #print(f"append note_on {delta=} {event.channel=}")
        elif event.type == "program_change":
            # Thiss necessary should there be different instruments
            # in the crank organ. 
            track.append( mido.Message( "program_change", program=event.program, channel=channel, time=delta))
            #print(f"program change {delta=} {event.channel=} {event.program=}")
        else:
            raise RuntimeError("Unprocessed midi event")
        # Can't simply do tracktime[channel] = start_time
        # Must do the calculation using the MIDI delta, 
        # if not rounding/truncating errors
        # will start to propagate getting significant at the end
        # of tunes.
        tracktime[channel] += delta * tempo_secs / ticks_per_beat
        # No need to output further "set tempo" meta events since event.time
        # already reflects the tempo changes

    midifile.save( output_filename )



def compress_midi_file( input_folder, filename, output_folder, force_compress, bass_correction ):
    pf = Path( filename )
    input_filename = Path(input_folder) / pf
    output_filename = (Path(output_folder) / pf).with_suffix( pf.suffix + ".gz")
    input_size, input_date = file_info(input_filename)
    output_size, output_date = file_info(output_filename)
    if input_date >= output_date or force_compress:
        print("Input file", filename, "processing...")
        print("    input", input_size, "bytes")
        reformat_midi( input_filename, "temp.mid", bass_correction )
        
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

def compare_folder_with_tunelib( folder, tunelib_file ):
    def compare( set1, set2 ):
        nt = []
        for fn in set1-set2:
            nt.append(fn)
        nt.sort()
        for fn in nt:
            print("    ", fn)
    def nfc( s ):
        return unicodedata.normalize( "NFC", s )
    
    TLCOL_FILENAME = 6
    # TLCOL_SIZE = 11
    if not tunelib_file:
        return

    with open(tunelib_file,encoding="utf8") as file:
        tunelib = json.load( file )
        
    tunelib_files = set( nfc(tune[TLCOL_FILENAME]) for tune in tunelib.values())
    folder_files = set( nfc(fn) for fn in os.listdir(folder) )
    print("In tunelib (microcontroller) but not in folder")
    compare( tunelib_files, folder_files )
    print("In folder but not in tunelib (microcontroller)")
    compare( folder_files, tunelib_files )
    
def main():
    input_folder, output_folder, force_compress, bass_correction, tunelib_file = parse_arguments()
    print(f"Input folder", input_folder)
    print(f"Output folder", output_folder)
    if tunelib_file:
        print(f"Tunelib file", tunelib_file )
        compare_folder_with_tunelib( output_folder, tunelib_file )

    input_blocks = 0
    output_blocks = 0
    input_bytes = 0
    output_bytes = 0
    n = 0
    max_decompressed_size = 0
    for filename in os.listdir( input_folder ):
        if filename.lower().endswith(".mid"):

            input_size, decompressed_size, output_size = compress_midi_file(
                input_folder, 
                filename, 
                output_folder, 
                force_compress, 
                bass_correction )
            
            max_decompressed_size = max(max_decompressed_size, decompressed_size)
            input_blocks += size_on_flash(input_size)
            output_blocks += size_on_flash(output_size)
            input_bytes += input_size
            output_bytes += output_size
            n += 1
    remove_deleted_files( input_folder, output_folder )

    if n == 0:
        # No files, no statistics
        return
    
    #print(f"Maximum decompressed size={max_decompressed_size} bytes")
    avg_output = output_blocks/n
    avg_input = input_blocks/n
    ratio = output_blocks/input_blocks
    print(f"{n} files {input_blocks=} {output_blocks=} (1 block=4096 bytes)")
    print(f"average input={avg_input:4.1f} blocks/file, average output={avg_output:4.1f} blocks/file, block compression {ratio=:4.2f}")
    print(f"average input={input_bytes/n/1000:4.0f} kbytes/file, average output={output_bytes/n/1000:4.0f} kbytes/file, bytes compression ratio={output_bytes/input_bytes:4.2f}")
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
    for flash_size in [8, 16]:
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
#434 files input_blocks=1884 output_blocks=822 (1 block=4096 bytes)
#average input= 4.3 blocks/file, average output= 1.9 blocks/file, block compression ratio=0.44
#average input=  16 kbytes/file, average output=   6 kbytes/file, bytes compression ratio=0.36
#Estimated capacities based on current average MIDI file size, no lyrics:
#N8R8 : raw capacity= 278, compressed capacity= 638 midi files
#N16R8: raw capacity= 750, compressed capacity=1719 midi files

