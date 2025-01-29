
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

import mido

this_file_py = Path(__file__).name
this_file = Path(__file__).stem
this_file_json = this_file + ".json"

DESC = """<this_file>.py
Compresses each .MID or .mid file in the input folder, writing the compressed file to the output folder. 
Strips all meta MIDI messages, and most channel messages leaving only note on, note off and program change. 
Incorporates all set_tempo indications in the output. 
Uses running status wherever possible, then compresses with gzip, adding a .gz to the file name.
Only compresses files newer than the compressed output file (can be overridden with -f)
Shows some statistics about the compression when finished.
Format is:
python <this_file>.py <input folder> <output folder>
Input and output folder need only be specified once. From then on, they
are stored in <this_file>.json in the current folder.
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
    args = parser.parse_args()
    if len(args.folders) >= 3:
        print("Can only specify two folders, the input and the output folder")
        sys.exit(1)
        
    try:
        with open(this_file_json) as file:
            j = json.load(file)
    except FileNotFoundError:
        if len(args.folders) != 2:
            print(f"No {this_file_json}, must specify input and output folder. Use --help to get command description")
            sys.exit(1)
        j = {}
    
    if args.folders:
        if len(args.folders) >= 1:
            j["input_folder"] = args.folders[0]
        if len(args.folders) >= 2:
            j["output_folder"] = args.folders[1]
        with open(this_file_json, "w") as file:
            json.dump( j, file )
    return j["input_folder"], j["output_folder"], args.force_compress
        

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
    #if size < 512:
    # but then, the inode should also be accounted for....
    #    return size/4096
    return (size+4095)//4096

def read_file( filename ):
    with open(filename, "rb") as file:
        return file.read()
    
def write_file( filename, data ):
    with open(filename, "wb") as file:
        file.write(data)

def read_midi( filename ):
    midifile = mido.MidiFile( filename )
    ticks_per_beat = midifile.ticks_per_beat
    event_list = [ event for event in midifile ]
    return event_list, ticks_per_beat

def reformat_midi( input_filename, output_filename ):
    # Get rid of all messages in the file except note on and note off.
    # Convert all note off messages to note on with velocity 0,
    # because running status will compress the raw midi file more.
    # Insert a program change to flute for each channel.
    # Assign one channel to each midi file track.
    # Insert one set tempo with a standard tempo, since the
    # timing is already taken care of.
    event_list, ticks_per_beat = read_midi( input_filename )
    # Override ticks per beat, we don't need so much precision
    # 48 ticks per beat = about 10 millisec smallest time resolution
    # 96 ticks per beat = about  5 millisec smallest time resolution
    # This will quantize the midi files a bit, just like a real
    # paper roll crank organ. There the quantization is about 30 millisec
    # but then it is much more controlled, since minimum length is
    # also about 30 milliseconds. But quantization in MIDI files is random,
    # while in the crank organ it is not (I hope)
    ticks_per_beat = 96
    try:
        last_time = event_list[0][0]
    except:
        last_time = 0

    midifile = mido.MidiFile()
    midifile.ticks_per_beat = ticks_per_beat

    trackdict = OrderedDict()
    # Make a track for meta messages and set tempo
    # No need anymore for track 0
    # Make a track dictionary with one track per channel
    for chan in set( event.channel for event in event_list if
                    event.type == "note_on" or
                    event.type == "note_off"):
        trackdict[chan] = [mido.MidiTrack(),last_time] 

    for track, _ in trackdict.values():
        midifile.tracks.append( track )
    
    tempo = 500_000
    # Insert one set_tempo event at the beginning of the first track, 
    # (just to be sure)
    # with standard tempo. Deltas will be adjusted to this tempo.
    track = list(trackdict.values())[0][0]
    track.append( mido.MetaMessage( type="set_tempo", tempo=tempo, time=0))
    
    # Insert a program change for all  channels
    # to change sound to a type of flute
    for channel, (track,_) in trackdict.items():
        if channel == 9:
            # Standard program for drum channel (channel 10)
            program = 0
        else:
            # A kind of flute for all other channels except drum
            program = 74
        track.append( mido.Message( type="program_change", program=program, time=0, channel=channel) )

    running_time = 0
    for event in event_list:
        # Calculate running time using all events. Not all
        # events are output, but running_time must consider
        # all events.
        running_time += event.time

        if not hasattr(event,"channel"):
            # Process only channel events, no meta/sysex.
            continue
        track_id = event.channel

        if track_id not in trackdict:
            # If channel does not have any note_on/note_off but only
            # other messages, it will be ignored here.
            continue
        
        # Get the MidiTrack and the running_time of the last event
        track, last_time = trackdict[track_id]
        # Now calculate the MIDI file delta time.
        delta = round( mido.second2tick( running_time-last_time, ticks_per_beat, tempo ) )
        #print(f"{event.time=} {last_time=} {ticks_per_beat=} {tempo=} {delta=}")
        if event.type == "note_on" or event.type == "note_off":
            velocity = 0
            if event.type == "note_on" and event.velocity != 0:
                # Use a fixed velocity
                velocity = 64
            # Use only Note On MIDI events, this will optimize
            # running status and yield smallest file.
            track.append( mido.Message( "note_on", note=event.note, velocity=velocity, time=delta, channel=event.channel ) )
            #print(f"append note_on {delta=} {event.channel=}")
            trackdict[track_id][1] = running_time
        elif event.type == "program_change":
            # This only necessary should there be different instruments
            # in the crank organ. 
            track.append( mido.Message( "program_change", program=event.program, channel=event.channel))
            #print(f"program change {delta=} {event.channel=} {event.program=}")
            trackdict[track_id][1] = running_time
        # No need to output further "set tempo" meta events since event.time
        # already reflects the tempo changes.

    midifile.save( output_filename )



def compress_midi_file( input_folder, filename, output_folder, force_compress ):
    pf = Path( filename )
    input_filename = Path(input_folder) / pf
    output_filename = (Path(output_folder) / pf).with_suffix( pf.suffix + ".gz")
    input_size, input_date = file_info(input_filename)
    output_size, output_date = file_info(output_filename)
    if input_date >= output_date or force_compress:
        print("Input file", filename, "processing...")
        print("    input", input_size, "bytes")
        reformat_midi( input_filename, "temp.mid")
        
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

def main():
    input_folder, output_folder, force_compress = parse_arguments()
    print(f"Input folder", input_folder)
    print(f"Output folder", output_folder)
    print("")
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
                force_compress )
            
            max_decompressed_size = max(max_decompressed_size, decompressed_size)
            input_blocks += size_on_flash(input_size)
            output_blocks += size_on_flash(output_size)
            input_bytes += input_size
            output_bytes += output_size
            n += 1
    remove_deleted_files( input_folder, output_folder )

    if n == 0:
        return
    #print(f"Maximum decompressed size={max_decompressed_size} bytes")
    avg_output = output_blocks/n
    avg_input = input_blocks/n
    ratio = output_blocks/input_blocks
    print(f"{n} files {input_blocks=} {output_blocks=} (1 block=4096 bytes)")
    print(f"average input={avg_input:4.1f} blocks/file, average output={avg_output:4.1f} blocks/file, block compression {ratio=:4.2f}")
    print(f"average input={input_bytes/n/1000:4.0f} kbytes/file, average output={output_bytes/n/1000:4.0f} kbytes/file, bytes compression ratio={output_bytes/input_bytes:4.2f}")
	# Dic 2024: overhead is 634 bloques, 512 for Micropython
	# rest for /data, /lib y /software
    # blocks approx including micropython, *.mpy, static, data (with compiled mpy files and compressed static files)
    # and data files, 4 error.log files, a tunelib.json and lyrics.json
    # with 2 backups each, estimated size.
    application_overhead = 720
    # If static is not compressed and micropython is not compiled
    application_overhead = 840
    print("Estimated capacities based on current average MIDI file size")
    for flash_size in [8, 16]:
        blocks = flash_size*1024*1024/4096
        blocks_free = blocks - application_overhead
        #print(f"{flash_size=} {blocks=} {blocks_free=}")
        input_capacity = round(blocks_free/avg_input)
        output_capacity = round(blocks_free/avg_output)
        model = f"N{flash_size}R8"
        print(f"{model:5s}: raw capacity={input_capacity:4.0f}, compressed capacity={output_capacity:4.0f} midi files")
    print("Application overhead does not consider heavy use of lyrics")

main()
    
# Decompressing takes somewhere between 200 ms and 800ms

#N16R8 os.statvfs("") with empty file system:
#  os.statvfs("")
# (4096, 4096, 3584, 3582, 3582, 0, 0, 0, 0, 255)
# means that overhead for micropython = 512 blocks = 2MB

# With ticks_per_beat = 48 and application_overhead = 670
#Maximum decompressed size=109329 bytes
#372 files input_blocks=1594 output_blocks=587
#average input=4.3 blocks/file average output=1.6 blocks/file ratio=0.37
#average input=15346 bytes/file average output=4362 bytes/file ratio=0.3
#N8R8 : raw capacity= 322 compressed capacity= 873 midi files
#N16R8: raw capacity= 800 compressed capacity=2171 midi files

# With ticks_per_beat = 96 and application_overhead = 670
#Maximum decompressed size=109331 bytes
#372 files input_blocks=1594 output_blocks=633
#average input=4.3 blocks/file average output=1.7 blocks/file ratio=0.40
#average input=15346 bytes/file average output=4799 bytes/file ratio=0.3
#N8R8 : raw capacity= 322 compressed capacity= 810 midi files
#N16R8: raw capacity= 800 compressed capacity=2013 midi files