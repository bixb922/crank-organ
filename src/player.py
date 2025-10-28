# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License


# Plays MIDI files using the umidiparser module
from micropython import const
from time import ticks_us, ticks_diff
import asyncio
import errno
from random import getrandbits

from umidiparser import NOTE_OFF, NOTE_ON, PROGRAM_CHANGE
from minilog import getLogger
from drehorgel import tunemanager, controller, battery, history, crank, config, timezone

import scheduler
from midi import DRUM_PROGRAM, DRUM_CHANNEL
from fileops import open_midi

CANCELLED = const("cancelled") 
ENDED = const("ended")
PLAYING = const("playing")

# Can also be "waiting", "file not found", others.

class MIDIPlayerProgress:
    def __init__(self):
        self.boot_session = hex(getrandbits(24))
        self.progress = {"tune": None, "playtime": 0, "status": ""}

    def tune_started(self, tuneid):
        self.progress = {"tune": tuneid, "playtime": 0, "status": PLAYING}

    def tune_ended(self):
        self.progress["status"] = ENDED

    def tune_cancelled(self):
        self.progress = {"tune": None, "playtime": 0, "status": CANCELLED}

    def report_exception(self, message):
        self.progress["status"] = message

    def get(self, time_played_us):
        self.progress["playtime"] = time_played_us / 1000
        self.progress["boot_session"] = self.boot_session
        return self.progress


class MIDIPlayer:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.time_played_us = 0
        self.progress = MIDIPlayerProgress()
        # Channel map has the current program number for each
        # channel. MIDI program numbers are 1 to 128. 
        # 0 means WILDCARD_PROGRAM (i.e. whatever matches) and
        # DRUM_PROGRAM is for drum instruments on MIDI channel 10
        self.channelmap = bytearray(16)

        # Default startup value for tempo follows crank, can ge changed
        # from play.html page
        self.set_tempo_follows_crank( config.cfg.get("tempo_follows_crank", False ) )
        self.logger.debug("init ok")
        
    async def play_tune(self, tuneid, requested ):
        try:
            self.time_played_us = 0
            battery.end_heartbeat()

            duration = 1 # Needed so finally does not fail.

            # get_info_by_id() could fail in case tunelib
            # has not been correctly updated. 
            midi_file, duration = tunemanager.get_info_by_tuneid(tuneid)
            if not midi_file:
                # tuneid not in tunelib
                self.logger.info(f"{tuneid} not found in tunelib")
                self.progress.report_exception("tuneid not found in tunelib.json")
                # Note that finally: will run anyhow
                return
            
            controller.all_notes_off()
            self.progress.tune_started(tuneid)
            self._reset_channelmap()

            # Start with garbage collector to stabilize gc performance
            scheduler.collect_garbage(reset=True)
            scheduler.collect_garbage()

            # activate the scheduler BEFORE starting to play
            # If not, a task might start just when the MIDI file starts
            # and then interfere with the timing of the notes.
            await scheduler.wait_and_yield_ms( 200 )
            start_time = timezone.now_timestamp()
            await self._play(midi_file)
            
            self.progress.tune_ended()

            # Let last minute pending blinks wind down
            await asyncio.sleep_ms(200)


        except asyncio.CancelledError:
            self.logger.debug("Player cancelled (next or da capo button, tuner)")
            self.progress.tune_cancelled()
        except OSError as e:
            if e.errno == errno.ENOENT:
                self.logger.info(f"File {midi_file=} or .gz {tuneid=} file not found")
                self.progress.report_exception("file not found")
                # Tell the tunemanager that the field has been deleted
                # so it can remove the tuneid from tunelib.json
                tunemanager.queue_file_deleted( midi_file )
            else:
                # OSError that isn't file not found - strange.
                self.logger.exc(e, f"Exception playing {midi_file=} or .gz {tuneid=}")
                self.progress.report_exception(
                    "exception in play_tune! " + str(e)
                )
        except Exception as e:
            self.logger.exc(e, f"play_tune+umidiparser {tuneid=}")
            self.progress.report_exception("exception in play_tune! " + str(e))
        finally:
            # End of tune processing and clean up
            controller.all_notes_off()
            scheduler.run_always()
            battery.start_heartbeat()
            battery.end_of_tune(self.time_played_us / 1_000_000)
            self._insert_history( tuneid, 
                                 start_time,
                                 self.time_played_us, 
                                 duration, 
                                 requested )
# 2025-08-28 10:09:33GMT-4 - setlist - DEBUG - Automatic playback sets music start event
# 2025-08-28 10:09:33GMT-4 - setlist - INFO - start tuneid=ivKpJWIoT
# 2025-08-28 10:09:33GMT-4 - player - INFO - ivKpJWIoT not found in tunelib
# 2025-08-28 10:09:34GMT-4 - tunemanager - INFO - Adding VR125_A035 Carmen toeador rvb 1.mid in tunelib.json
# main._handle_exception: unhandled asyncio exception {'future': <Task>, 'message': "Task exception wasn't retrieved", 'exception': NameError('local variable referenced before assignment',)}
# 2025-08-28 10:09:34GMT-4 - startup - EXCEPTION - asyncio global exception handler
#        Traceback (most recent call last):
#          File "asyncio/core.py", line 1, in run_until_complete
#          File "/software/mpy/setlist.py", line 145, in _setlist_process
#          File "asyncio/core.py", line 1, in run_until_complete
#          File "/software/mpy/player.py", line 128, in play_tune
#        NameError: local variable referenced before assignment
       

    def _insert_history(self, tuneid, start_time, time_played_us, duration, requested):
        try:
            percentage_played = round(time_played_us / 1000 / duration * 100)
        except ZeroDivisionError:
            percentage_played = 0
        history.add_entry(tuneid, start_time, percentage_played, requested)
        if percentage_played > 95:
            tunemanager.add_one_to_history( tuneid )

    def _reset_channelmap(self):
        for i in range(len(self.channelmap)):
            self.channelmap[i] = 1 # 1=piano as default program number
        # Channel 10 always are drum notes, assign the virtual DRUM PROGRAM
        # to all the notes that are played on ths channel. Program change
        # events are ignored on channel 10, see self._process_midi()
        # Use the (virtual) DRUM_PROGRAM number for this channel
        self.channelmap[DRUM_CHANNEL] = DRUM_PROGRAM
    

    async def _play(self, midi_file):

        # MidiFile() file takes about 50 millisec on a ESP32-S3 at 240 Mhz, 
        # do it before
        # starting the for event in midifile loop.
        # fileops.open_midi() takes 200 to 400 ms to decompress a gz
        # file and to create temp.mid and open it with MidiFile()
        midifile = open_midi( midi_file ) # fileops.open_midi

        self.time_played_us = 0  # Sum of delta_us prior to tachometer adjust

        # Leave some time to process possible events previous
        # to start of music. This can be important if there are
        # a lot of meta events with lots of text before the first note.
        # 500 msec should be enough, I have found one case of 240 msec.
        # This should not be an issue for MIDI files compressed with
        # compress_midi.py, since all meta events are skipped.
        playing_started_at = ticks_us() + 500_000
        midi_time = 0
        for midi_event in midifile:
            # CPU time 1076 usec/event average (May2025)
            # Sample file with 5576 events in 102 seconds, means
            # average CPU usage of 5.8%

            # Optimization: skip events that don't matter
            # in _process_midi(), only NOTE_ON, NOTE_OFF and PROGRAM_CHANGE
            # events are important.
            # But if delta_us != 0, the event has to be processed
            # to update time.
            # (No gain for MIDI files compressed with compress_midi.py)
            if midi_event.delta_us == 0 and not midi_event.is_channel():
                continue

            # midi_time is the calculated MIDI time since the start of the MIDI file
            # Without tachometer: midi_time += midi_event.delta_us      
            midi_time += await self._calculate_tachometer_dt( midi_event.delta_us ) # type:ignore

            # playing_time is the wall clock time since playing started
            playing_time = ticks_diff(ticks_us(), playing_started_at)

            # Wait for the difference between the "time that is" and 
            # the "time that should be"
            wait_time = round(midi_time - playing_time)
            # >>> measure jitter again?
            # >>> end tune if MIDI suspended for a long time, i.e. tune forgotten?
            # >>> end tune if MIDI suspended very near the end of the tune?
            # >>> make that a config parameter?
            # Sleep until scheduled time has elapsed
            await scheduler.wait_and_yield_ms( wait_time )

            # time_played_us goes from 0 to the length of the midi file in microseconds
            # and is not affected by playback speed. Is used to calculate
            # % of s
            self.time_played_us += midi_event.delta_us # type:ignore
            # Turn one note on or off.
            self._process_midi(midi_event)

    def _process_midi(self, midi_event):
        status = midi_event.status
        # Process note off event (equivalent to note on, velocity 0)
        if (
            status == NOTE_ON
            and midi_event.velocity == 0
        ) or status == NOTE_OFF:
            controller.note_off( 
                    self.channelmap[midi_event.channel], 
                    midi_event.note)
        # Process note on event
        elif status == NOTE_ON:
            controller.note_on( 
                    self.channelmap[midi_event.channel], 
                    midi_event.note)
        # Process program change
        elif status == PROGRAM_CHANGE and midi_event.channel != DRUM_CHANNEL:
            # Allow program change only for non-percussion channels
            # Internally program_number will be 1-128 for MIDI
            # to leave 0 for WILDCARD_PROGRAM and 129 for DRUM_PROGRAM
            self.channelmap[midi_event.channel] = midi_event.program+1

        # umidiparser already handled the set tempo meta event, no
        # need to process here.

    def get_progress(self):
        p = self.progress.get(self.time_played_us)
        p["tempo_follows_crank"] = self.tempo_follows_crank
        return p
    
    async def _calculate_tachometer_dt(self, midi_event_delta_us):
        # Recompute delta time due to crank or UI velocity setting
        additional_wait = 0
        # >>> check this if.
        if not self.tempo_follows_crank or crank.is_turning():
            # Change playback speed with UI settings 
            # and with crank rpsec if crank sensor is enabled
            normalized_vel = crank.get_normalized_rpsec(self.tempo_follows_crank)
            if normalized_vel < 0.1:
                # Avoid division by zero.
                # Also a very slow speed is meaningless here, 
                # crank should inform that it has stopped...?
                normalized_vel = 1
            additional_wait = round(midi_event_delta_us / normalized_vel)
            # >>>SHOULD RETURN HERE?


        # We get here if the crank is not turning and tempo_follows_crank is enabled.
        # Wait for the crank to start turning again and return the waiting time
        # to be added to the MIDI time delaying the rest of the tune.
        if not crank.is_turning() and crank.is_installed():
            additional_wait += await self._wait_for_crank_to_turn()

        return additional_wait
    
    async def _wait_for_crank_to_turn( self ):
         # Turning too slow or stopped, wait until crank turning
        # and return the waiting time. MIDI time is then delayed
        # by the same amount than the time waiting for the crank to turn
        # again, so playing can resume without a hitch.
        self.logger.debug("waiting for crank to turn")
        start_wait = ticks_us()
        # Don't let a note on during wait, it may
        # be realistical but it's not nice
        controller.all_notes_off()
        # Wait for the crank to start turning
        await crank.wait_start_turning()

        # Lengthen MIDI time by the wait
        return ticks_diff(ticks_us(), start_wait)

    def set_tempo_follows_crank( self, v ):
        # Store setting
        # If crank not installed, don't follow crank....
        self.tempo_follows_crank = v and crank.is_installed()
        