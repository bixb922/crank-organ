
import time
import asyncio
import json
import errno
import os
import array

import config
import umidiparser
import solenoid
from minilog import getLogger
import tunelist
import tachometer
import scheduler
import modes
import midi


CANCELLED = const("cancelled")
ENDED = const("ended")
PLAYING = const("playing")
# Can also be "waiting", "file not found", others


def _init( ):
    global _logger, _time_played_us, _progress
    _logger = getLogger( __name__ )
         
    # Initialize variables used during playback to indicate progress
    _time_played_us = 0
    _progress = { "tune": None, "playtime": 0, "status": "" }
    _logger.debug("init ok")
    
    
async def play_tune( tune, stop_event ):
    global _time_played_us
    try:
        _time_played_us = 0
        midi_file = tunelist.get_filename_by_number(tune)
        solenoid.all_notes_off() 
        _progress["tune"] = tune
        _progress["playtime"] = 0
        _progress["status"] = PLAYING
        _logger.info(f"Starting tune {tune} {midi_file}")
        _reset_channelmap()
      
        await _play_with_tachometer( midi_file, stop_event )
        _progress["status"] = ENDED
        
    except OSError as e:
        if e.errno == errno.ENOENT:
            _logger.error(f"File {midi_file=} {tune=} file not found") 
            _progress["status"] = "file not found"
        else:
            _logger.exc(e, f" play_tune umidiparser {midi_file=} {tune=}" )
            _progress["status"] = "exception in play_tune! " + str(e)
    except Exception as e:
        _logger.exc(e,  f"play_tune+umidiparser {midi_file=} {tune=}" )
        _progress["status"] = "exception in play_tune! " + str(e)
    finally:
        solenoid.all_notes_off()
        scheduler.run_always()

def get_progress( ):
    global _time_played_us, _progress
    
    _progress["playtime"] = _time_played_us/1000
    # webserver.py will add more info to the progress dict,
    # for example the setlist
    return _progress


async def _wait_for_play_mode():
    while not modes.is_play_mode():
        await scheduler.wait_and_yield_ms( 500 )


# The channelmap contains the current program for each channel
channelmap = bytearray(16)
def _reset_channelmap():
    for i in range(len(channelmap)):
        channelmap[i] = 0
    # Percussion channels use the fixed "virtual" DRUM_PROGRAM number
    # Channel map uses program numbers 0 to 127.
    # The Note class needs program numbers 1 to 128, 
    # and DRUM_PROGRAM==129 for the special program used in channels 10
    # and 11.
    # +1 gets added in midi_event_to_note
    channelmap[10] = midi.DRUM_PROGRAM-1
    channelmap[11] = midi.DRUM_PROGRAM-1
        
def midi_event_to_note( midi_event ):
    # The Note class needs program numbers in the range 1-128
    return midi.Note( channelmap[midi_event.channel]+1, midi_event.note )

def _process_midi( midi_event ):
    if (midi_event.status == umidiparser.NOTE_OFF or
         (midi_event.status == umidiparser.NOTE_ON and midi_event.velocity == 0) ):
        solenoid.note_off( midi_event_to_note( midi_event ) )
    elif midi_event.status == umidiparser.NOTE_ON and midi_event.velocity != 0:
        solenoid.note_on( midi_event_to_note( midi_event )  )
    elif midi_event.status == umidiparser.PROGRAM_CHANGE:
        if not( 10 <= midi_event.channel <= 11):
            # Allow program change only for non-percussion channels
            channelmap[midi_event.channel] = midi_event.program
        
            
async def _play_with_tachometer(  midi_file, stop_event ):
    global _time_played_us
    
    # Open MIDI file takes about 50 millisec on a ESP32-S3 at 240 Mhz, do it before
    # starting the loop.
    bufsiz = 0 if config.large_memory else 100
    midifile = umidiparser.MidiFile( midi_file, buffer_size=bufsiz )
    
    _time_played_us = 0 # Sum of delta_us prior to tachometer adjust
    playing_started_at = time.ticks_us()
    midi_time = 0
    
    for midi_event in midifile:
        # Stall if not in play mode.
        await _wait_for_play_mode()
        
        # Calculate dt = time difference in event time due to tachometer
        # being faster or slower than normal
        dt = await _calculate_tachometer_dt( midi_event.delta_us, stop_event )
        # midi_time is the calculated MIDI time since the start of the MIDI file
        midi_time += (midi_event.delta_us + dt)
        # playing_time is the clock time since playing started
        playing_time = time.ticks_diff( time.ticks_us(), playing_started_at )

        # Wait for the difference between the time that is and the time that
        # should be
        wait_time = midi_time - playing_time

        
        # Sleep until scheduled time has elapsed
        await scheduler.wait_and_yield_ms( round(wait_time/1000) )
        
        # _time_playedys goes from 0 to the length of the midi file in microseconds
        # and is not affected by playback speed. Is used to calculate
        # % of progress.
        _time_played_us += midi_event.delta_us

           
        # Turn one note on or off.
        _process_midi( midi_event )

            
        # Stop playing signaled? This happens if the user hits "next" button
        if stop_event.is_set():
            stop_event.clear()
            solenoid.all_notes_off()
            _logger.info(f"current tune {midi_file} cancelled")
            _progress["status"] = CANCELLED
            _progress["tune"] = None
            _progress["playtime"] = 0
            _time_played_us = 0
            break

         
async def _calculate_tachometer_dt( midi_event_delta_us, stop_event ):
    if not tachometer.tachometer_pin:
        return 0
    # Calculate dt, difference of time due to
    # crank turning speed
    tmeter_vel = tachometer.get_normalized_rpsec() 
    if tachometer.is_turning() and tmeter_vel != 0:
        # Calculate dt = difference of midi_event.delta_us and the
        # time it should be
        dt = int( midi_event_delta_us / tmeter_vel ) - midi_event_delta_us
    else:
        # Turning too slow or stopped, wait until crank turning
        # but also exit if stop_event signals that tune should be stopped.
        start_wait = time.ticks_us()
        _logger.debug("waiting for crank to turn")
        solenoid.all_notes_off()
        while True:
            if tachometer.is_turning() or stop_event.is_set():
                break
            await scheduler.wait_and_yield_ms( 300 )
        # Add all time waited to dt
        dt = time.ticks_diff( time.ticks_us(), start_wait )
    return dt
      

_init() 
