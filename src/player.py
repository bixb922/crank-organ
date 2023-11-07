# (c) 2023 Hermann Paul von Borries
# MIT License
# Plays MIDI files using the umidiparser module
import time
import asyncio
import json
import errno
import os
import array

from config import config
import umidiparser
from solenoid import solenoid
from minilog import getLogger
from tunemanager import tunemanager
import scheduler
import midi
from battery import battery
from history import history
import tachometer

CANCELLED = const("cancelled")
ENDED = const("ended")
PLAYING = const("playing")
# Can also be "waiting", "file not found", others

class MIDIPlayerProgress:
    def __init__( self ):
        self.progress = { "tune": None, "playtime": 0, "status": "" }        
        
    def tune_started( self, tuneid ):
        self.progress = { "tune": tuneid, "playtime": 0, "status": PLAYING }
        
    def tune_ended( self ):
        self.progress[ "status" ] = ENDED

    def tune_cancelled( self ):
        self.progress = { "tune": None, "playtime": 0, "status": CANCELLED }

    def report_exception( self, message ):
        self.progress["status"] = message
    
    def get( self, time_played_us ):
        self.progress["playtime"] = time_played_us/1000
        return self.progress
  
class MIDIPlayer:
    def __init__( self ):
        self.logger = getLogger( __name__ )
        self.time_played_us = 0
        self.progress = MIDIPlayerProgress( )
        # Channel map has current program number for each
        # channel
        self.channelmap = bytearray( 16 )
    
        self.logger.debug( "init ok" ) 
        
    async def play_tune( self, tuneid ):
        try:
            self.time_played_us = 0
            battery.end_battery_heartbeat()
            midi_file = tunemanager.get_filename_by_id( tuneid )
            duration = tunemanager.get_duration( tuneid )         
            solenoid.all_notes_off()       
            self.progress.tune_started( tuneid )
            self._reset_channelmap()
            self.logger.info(f"Starting tune {tuneid} {midi_file}") 
            
            await self._play( midi_file )
            
            self.progress.tune_ended()

        except asyncio.CancelledError:
            self.logger.debug("Player cancelled")
            solenoid.all_notes_off()
            self.progress.tune_cancelled()

        except OSError as e:
            if e.errno == errno.ENOENT:
                self.logger.error(f"File {midi_file=} {tuneid=} file not found") 
                self._report_exception( "file not found")
            else:
                self.logger.exc(e, f"Exception playing {midi_file=} {tuneid=}" )
                self.progress.report_exception( "exception in play_tune! " + str(e) )
        except Exception as e:
            self.logger.exc(e,  f"play_tune+umidiparser {tuneid=}" )
            self.progress.report_exception( "exception in play_tune! " + str(e) )
        finally:
            self.logger.debug(f"finally section reached")
            try:
                history_percentage = round(self.time_played_us / 1000 / duration * 100)
                self.logger.debug(f"add history {tuneid} {self.time_played_us=} {duration=}  {history_percentage=}")
                history.add_entry( tuneid, history_percentage )
            except Exception as e:
                self.logger.exc(e, "Exception adding history")
            solenoid.all_notes_off()
            scheduler.run_always()
            battery.start_battery_heartbeat()

            # The channelmap contains the current program for each channel

    def _reset_channelmap( self ):
        for i in range(len(self.channelmap)):
            self.channelmap[i] = 0
        # Percussion channels use the fixed "virtual" DRUM_PROGRAM number
        # Channel map uses program numbers 0 to 127.
        # The Note class needs program numbers 1 to 128, 
        # and DRUM_PROGRAM==129 for the special program used in channel 10
        # +1 gets added in midi_event_to_note
        self.channelmap[10] = midi.DRUM_PROGRAM-1

        
    def _midi_event_to_note( self, midi_event ):
        # The Note class needs program numbers in the range 1-128
        return midi.Note( self.channelmap[midi_event.channel]+1, midi_event.note )

          
    async def _play( self, midi_file ):

        # Open MIDI file takes about 50 millisec on a ESP32-S3 at 240 Mhz, do it before
        # starting the loop.
        # With 4 to 8 MB RAM, there is enough to have large buffer. 
        # But no need to read the full file to memory
        midifile = umidiparser.MidiFile( midi_file, buffer_size=5000 )

        self.time_played_us = 0 # Sum of delta_us prior to tachometer adjust
        playing_started_at = time.ticks_us()
        midi_time = 0
        #plist = [] # >>>> DEBUG
        
        for midi_event in midifile:
            # midi_time is the calculated MIDI time since the start of the MIDI file
            #midi_time += midi_event.delta_us
            midi_time += await self._calculate_tachometer_dt( midi_event.delta_us )
            # playing_time is the clock time since playing started
            playing_time = time.ticks_diff( time.ticks_us(), playing_started_at )

            # Wait for the difference between the time that is and the time that
            # should be
            wait_time = midi_time - playing_time


            # Sleep until scheduled time has elapsed
            await scheduler.wait_and_yield_ms( round(wait_time/1000) )
            
# Debug: analyze if playing time is exact
#            p = time.ticks_diff( time.ticks_us(),
#                                playing_started_at )
#            plist.append( midi_time-p )
#            if len(plist)>30:
#                avgdiff = sum( plist )/len( plist )/1000
#                maxdiff = max(abs(x) for x in plist)/1000
#                if abs(maxdiff) >= 0:
#                    print(f"player {avgdiff=:.0f} {maxdiff=:.0f}")
#                plist = []
                
            # time_played_us goes from 0 to the length of the midi file in microseconds
            # and is not affected by playback speed. Is used to calculate
            # % of s
            self.time_played_us += midi_event.delta_us
            # Turn one note on or off.
            self._process_midi( midi_event )
            
    def _process_midi( self, midi_event ):
        # Process note off event (or note on velocity 0)
        if (midi_event.status == umidiparser.NOTE_OFF or
             (midi_event.status == umidiparser.NOTE_ON and midi_event.velocity == 0) ):
            solenoid.note_off( self._midi_event_to_note( midi_event ) )
        # Process note on event
        elif (midi_event.status == umidiparser.NOTE_ON 
              and midi_event.velocity != 0):
            solenoid.note_on( self._midi_event_to_note( midi_event )  )
        # Process program change
        elif midi_event.status == umidiparser.PROGRAM_CHANGE:
            if not( midi_event.channel == 10):
                # Allow program change only for non-percussion channels
                self.channelmap[midi_event.channel] = midi_event.program
        # umidiparser handles set tempo meta event.

    def get_progress( self ):
        return self.progress.get( self.time_played_us )
          
    
    async def _calculate_tachometer_dt( self, midi_event_delta_us ):
        # Transforms midi_event_delta in a time difference
        # according to tachometer speed
        # Calculate dt, difference of time due to
        # crank turning speed
        if ( not tachometer.is_installed() or (       
            tachometer.is_turning() and tmeter_vel != 0
            ) ):
             tmeter_vel = tachometer.get_normalized_rpsec() 
             return round( midi_event_delta_us / tmeter_vel ) 
        else:
            # Turning too slow or stopped, wait until crank turning
            start_wait = time.ticks_us()
            self.logger.debug("waiting for crank to turn")
            solenoid.all_notes_off()
            while True:
                if tachometer.is_turning():
                    break
                await scheduler.wait_and_yield_ms( 100 )
            # Make the time equal to the wait
            return time.ticks_diff( time.ticks_us(), start_wait )


        
player = MIDIPlayer()
