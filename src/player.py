# (c) 2023 Hermann Paul von Borries
# MIT License
# Plays MIDI files using the umidiparser module
from micropython import const
import time
import asyncio
import errno
from random import getrandbits

from umidiparser import NOTE_OFF, NOTE_ON, PROGRAM_CHANGE, MidiFile
from minilog import getLogger
from tunemanager import tunemanager
import scheduler
from midi import controller, DRUM_CHANNEL
from battery import battery
from history import history
from tachometer import crank
from config import config
from midi import DRUM_PROGRAM

CANCELLED = const("cancelled") # type: ignore
ENDED = const("ended") # type: ignore
PLAYING = const("playing") # type: ignore

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
        # Register event when cranking starts (0 msec after start)
        # This is used to know when to restart if cranking stops
        # during playback.
        self.crank_start_event = crank.register_event(0)
        # Default startup value for tempo follows crank
        self.set_tempo_follows_crank( config.cfg.get("tempo_follows_crank", False ) )
        self.logger.debug("init ok")
        
    async def play_tune(self, tuneid, requested ):
        try:
            self.time_played_us = 0
            battery.end_heartbeat()

            duration = 1
            # get_info_by_id could fail in case tunelib
            # has not been correctly updated
            midi_file, duration = tunemanager.get_info_by_tuneid(tuneid)

            controller.all_notes_off()
            self.progress.tune_started(tuneid)

            self._reset_channelmap()

            await self._play(midi_file)
            self.progress.tune_ended()

        except asyncio.CancelledError:
            self.logger.debug("Player cancelled")
            self.progress.tune_cancelled()

        except OSError as e:
            if e.errno == errno.ENOENT:
                self.logger.error(f"File {midi_file=} {tuneid=} file not found")
                self.progress.report_exception("file not found")
            else:
                self.logger.exc(e, f"Exception playing {midi_file=} {tuneid=}")
                self.progress.report_exception(
                    "exception in play_tune! " + str(e)
                )
        except Exception as e:
            self.logger.exc(e, f"play_tune+umidiparser {tuneid=}")
            self.progress.report_exception("exception in play_tune! " + str(e))
        finally:
            # End of tune processing and clean up
            controller.all_notes_off()
            try:
                self._insert_history(
                    tuneid, self.time_played_us, duration, requested
                )
            except Exception as e:
                self.logger.exc(e, "Exception adding history")
            scheduler.run_always()
            battery.start_heartbeat()
            battery.end_of_tune(self.time_played_us / 1_000_000)

    def _insert_history(self, tuneid, time_played_us, duration, requested):
        if duration > 0:
            percentage_played = round(time_played_us / 1000 / duration * 100)
        else:
            # Avoid division by 0
            self.logger.info(f"MIDI file {tuneid} has duration 0")
            percentage_played = 0
            
        self.logger.debug(
            f"add history {tuneid} {time_played_us=} {duration=}  {percentage_played=}"
        )
        history.add_entry(tuneid, percentage_played, requested)
        if percentage_played > 95:
            tunemanager.add_one_to_history( tuneid )

    def _reset_channelmap(self):
        for i in range(len(self.channelmap)):
            self.channelmap[i] = 1 # 1=piano as default program number
        # Channel 10 always are drum notes, assign the virtual DRUM PROGRAM
        # to all the notes that are played on ths channel. Program change
        # events are ignored on channel 10
        # Use the (virtual) DRUM_PROGRAM numbert for this channel
        self.channelmap[DRUM_CHANNEL] = DRUM_PROGRAM
    

    async def _play(self, midi_file):
        # Open MIDI file takes about 50 millisec on a ESP32-S3 at 240 Mhz, 
        # do it before
        # starting the loop.
        # With 4 to 8 MB RAM, there is enough to have large buffer.
        # But even so, there is no need to read the full file to memory
        # A buffer size of > 1000 means almost no impact on CPU
        midifile = MidiFile(midi_file, 
										buffer_size=5000,
									    reuse_event_object=True)
        self.time_played_us = 0  # Sum of delta_us prior to tachometer adjust
        playing_started_at = time.ticks_us()
        midi_time = 0

        for midi_event in midifile:
            # midi_time is the calculated MIDI time since the start of the MIDI file
            # midi_time += midi_event.delta_us
            midi_time += await self._calculate_tachometer_dt(
                midi_event.delta_us
            )
            # playing_time is the clock time since playing started
            playing_time = time.ticks_diff(time.ticks_us(), playing_started_at)

            # Wait for the difference between the time that is and the time that
            # should be
            wait_time = midi_time - playing_time

            # Sleep until scheduled time has elapsed
            await scheduler.wait_and_yield_ms(round(wait_time))
            # time_played_us goes from 0 to the length of the midi file in microseconds
            # and is not affected by playback speed. Is used to calculate
            # % of s
            self.time_played_us += midi_event.delta_us
            # Turn one note on or off.
            self._process_midi(midi_event)

    def _process_midi(self, midi_event):
        status = midi_event.status
        # Process note off event (equivalent to note on, velocity 0)
        if status == NOTE_OFF or (
            status == NOTE_ON
            and midi_event.velocity == 0
        ):
            controller.note_off( 
                    self.channelmap[midi_event.channel], 
                    midi_event.note)
        # Process note on event
        elif status == NOTE_ON:
            controller.note_on( 
                    self.channelmap[midi_event.channel], 
                    midi_event.note)
        # Process program change
        elif status == PROGRAM_CHANGE:
            if midi_event.channel != DRUM_CHANNEL:
                # Allow program change only for non-percussion channels
                # Internally program_number will be 1-128 for MIDI
                # to leave 0 for WILDCARD_PROGRAM and 129 for DRUM_PROGRAM
                self.channelmap[midi_event.channel] = midi_event.program+1
        # umidiparser handles set tempo meta event.

    def get_progress(self):
        p = self.progress.get(self.time_played_us)
        p["tempo_follows_crank"] = self.tempo_follows_crank
        return p

    async def _calculate_tachometer_dt(self, midi_event_delta_us):
        if not self.tempo_follows_crank or crank.is_turning():
            # Change playback speed with UI settings 
            # and with crank rpsec if crank sensor is enabled
            normalized_vel = crank.get_normalized_rpsec(self.tempo_follows_crank)
            if normalized_vel < 0.1:
                # Avoid division by zero.
                # Also a very slow
                # speed is meaningless here, crank should be stopped...?
                normalized_vel = 1
            return round(midi_event_delta_us / normalized_vel)

        # Turning too slow or stopped, wait until crank turning
        # and return the waiting time. MIDI time is then delayed
        # by the same amount than the time waiting for the crank to turn
        # again, so playing can resume without a hitch.
        self.logger.debug("waiting for crank to turn")
        start_wait = time.ticks_us()
        # Don't let a note on during wait, it may
        # be realistical but it's not nice
        controller.all_notes_off()
        # Wait for the crank to start turning
        self.crank_start_event.clear()
        await self.crank_start_event.wait()
        # Lengthen MIDI time by the wait
        return time.ticks_diff(time.ticks_us(), start_wait)

    def set_tempo_follows_crank( self, v ):
        # If crank not installed, don't follow crank....
        self.tempo_follows_crank = v and crank.is_installed()
        
# Singleton instance of player:
player = MIDIPlayer()
