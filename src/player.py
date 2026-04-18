# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License


# Plays MIDI files using the umidiparser module
from micropython import const
from time import ticks_us, ticks_diff, ticks_ms
import asyncio
from random import getrandbits

from umidiparser import NOTE_OFF, NOTE_ON, PROGRAM_CHANGE, AFTERTOUCH
from minilog import getLogger
from drehorgel import tunemanager, controller, battery, history, crank, config, timezone

import scheduler
from midi import DRUM_PROGRAM, DRUM_CHANNEL, NoteDef
from fileops import open_midi
from actuatorstats import ActuatorStats

CANCELLED = const("cancelled") 
ENDED = const("ended")
PLAYING = const("playing")

_PROCESSABLE_EVENTS = (NOTE_ON, NOTE_OFF, PROGRAM_CHANGE, AFTERTOUCH)
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

    def get(self):
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
        self.channelmap1 = bytearray(16)

        # Default startup value for tempo follows crank, can ge changed
        # from play.html page. Can be changed with UI. Will
        # reset after each tune
        self.set_tempo_follows_crank( config.tempo_follows_crank )
        self.current_note = NoteDef( 0, 0 )
        self.repeats = 0
        
        self.process_map = {
            NOTE_ON:  lambda c, d, n: controller.note_on( n ),
            NOTE_OFF: lambda c, d, n: controller.note_off( n ),
            PROGRAM_CHANGE: self._program_change,
            0xd0: self.processd0,
            0: lambda _: None # RFU
        }

        self.logger.debug("init ok")

    async def play_tune(self, tuneid ):

        # tuneid was removed from setlist just before this call
        # Make sure tuneid appears in progress["tune"]
        self.progress.tune_started(tuneid)
 
        # Start with garbage collector to stabilize gc performance
        scheduler.collect_garbage(reset=True)

        # activate the scheduler BEFORE starting to play
        # If not, a task might start just when the MIDI file starts
        # and would then interfere with the timing of the notes.
        await scheduler.wait_and_yield_usec( 30_000 ) # must be be > _RESERVED_USEC

        # Assign variables here so finally: does not fail for "local variable referenced before assignment"
        self.time_played_us = 0
        start_time = timezone.now_timestamp()
        midi_fn = None
        duration = 1 
        title = None
        self.repeats = 0
        midifile = None
        
        try:
            battery.end_heartbeat()
            # get_info_by_id() could fail in case tunelib
            # has not been correctly updated. 
            midi_fn, duration, title = tunemanager.get_info_by_tuneid(tuneid)
            if not midi_fn:
                # tuneid not in tunelib. Could be reported better in history
                # or shown in play page?
                self.logger.info(f"{tuneid} not found in tunelib or file not found")
                self.progress.report_exception("tune not found")
                # Note that finally will run anyhow
                return
            # Get MidiFile object
            midifile = open_midi( midi_fn ) # fileops.open_midi
            self.process_map[0]( midifile )
            if midifile.format_type not in (0,1):
                # Should not happen, only type 0 and 1 files are supported.
                self.logger.info(f"Invalid MIDI file format {midifile.format_type} for '{title}' {midi_fn}")
                return
            self.logger.info(f"Start {tuneid=} '{title}' tracks={len(midifile.tracks)}" )
            controller.all_notes_off()
            ActuatorStats.zero()
            # From play_tune from tunemanager to _play = 150 msec
            # In "barrel organ mode", repeat until
            # user presses button to get to next tune.
            for _ in range( 9999 if config.barrel_mode else 1):
                self.repeats += 1
                await self._play(midifile)
            self.progress.tune_ended()

            # Let last minute pending blinks wind down
            await asyncio.sleep_ms(100)

        except asyncio.CancelledError:
            self.logger.debug("Player cancelled (next or da capo button, tuner)")
            self.progress.tune_cancelled()
        except Exception as e:
            self.logger.exc(e, f"play_tune+umidiparser {tuneid=} '{title}' {midi_fn=}")
            self.progress.report_exception("exception in play_tune! " + str(e))
        finally:
            if midifile:
                midifile.finalize()
                del midifile
            # Get stats before turning off all notes, all notes off does not count.
            stats = ActuatorStats.get()
            # End of tune processing and clean up
            # Do this before scheduler frees async for all:
            controller.all_notes_off()
            # Let async tasks run freely
            # This will also run all pending scheduled tasks
            scheduler.run_always()
            self.logger.info(f"End {tuneid=} '{title}' {midi_fn=}, played {self.time_played_us/1_000_000:.2f}s of {duration/1_000:.2f}s")
            s = ", ".join( f"{k}={v}" for k,v in stats.items())
            self.logger.info(f"Actuator stats: {s}")
            battery.start_heartbeat()
            battery.end_of_tune(self.time_played_us / 1_000_000)
            self._insert_history( tuneid, 
                                start_time,
                                self.time_played_us + duration*1000*(self.repeats-1), 
                                duration )
            # scheduler.fdump() # for debug 
            
    def _insert_history(self, tuneid, start_time, time_played_us, duration ):
        try:
            percentage_played = round(time_played_us / 1000 / duration * 100)
        except ZeroDivisionError:
            percentage_played = 0
        history.add_entry(tuneid, start_time, percentage_played, 0 )
        
        # Now done in the browser:
        #if percentage_played > 95:
        #    tunemanager.add_one_to_history( tuneid )

    def _reset_channelmap1(self):
        for i in range(len(self.channelmap1)):
            self.channelmap1[i] = 1 # 1=piano as default program number
        # Channel 10 always are drum notes, assign the virtual DRUM PROGRAM
        # to all the notes that are played on ths channel. Program change
        # events are ignored on channel 10, see self._process_midi()
        # Use the (virtual) DRUM_PROGRAM number for this channel
        self.channelmap1[DRUM_CHANNEL] = DRUM_PROGRAM
    

    async def _play(self, midifile, delay_start=50_000 ):
        
        self._reset_channelmap1()
        self.time_played_us = 0  # Sum of delta_us prior to tachometer adjust
        # Leave some time to process possible events previous
        # to start of music. This can be important if there are
        # a lot of meta events with long texts before the first note.
        # There are cases with 100 program changes + control changes and other
        # crowded MIDI files.
        # 50 msec should be enough,
        # This should not be an issue for MIDI files compressed with
        # compress_midi.py, since all meta events have been stripped.
        playing_started_at = ticks_us() + delay_start
        midi_time = 0
        # Performance measurement
        msec_start = ticks_ms() 
        sum_real_waits = 0
        sum_scheduled_waits = 0
        midi_events = 0
        for midi_event in midifile:
            midi_events += 1
            # time_played_us goes from 0 to the length of the midi file in microseconds
            # and is not affected by playback speed. Is used to calculate
            # % of tune played.
            self.time_played_us += midi_event.delta_us # type:ignore

            # Optimization: skip events that don't matter
            # in _process_midi(), only NOTE_ON, NOTE_OFF and PROGRAM_CHANGE
            # events are processed here.
            # But if delta_us != 0, the event has to be processed
            # to update time.
            # (No gain for MIDI files compressed with compress_midi.py)
            status = midi_event.status
            if status == NOTE_ON and midi_event.velocity == 0:
                # Note on with velocity 0 is equivalent to note off
                status = NOTE_OFF
            if midi_event.delta_us == 0 and status not in _PROCESSABLE_EVENTS:
                continue
            
            # midi_time is the calculated MIDI time since the start of the MIDI file
            # Without tachometer: midi_time += midi_event.delta_us    
            midi_time += await self._calculate_tachometer_dt( midi_event.delta_us )

            # playing_time is the wall clock time since playing started
            playing_time = ticks_diff(ticks_us(), playing_started_at)

            # Wait for the difference between the "time that is" and 
            # the "time that should be"
            wait_time = round(midi_time - playing_time)

            if wait_time > 5000:
                # _process_midi() takes about 1.5 msec,
                # no need to process wait_and_yield for that.
                # Worst case: this note may be a bit early.
                # Best case: next notes will be on time if delta_us is small or zero

                # Sleep until scheduled time has elapsed
                t1 = ticks_us()
                await scheduler.wait_and_yield_usec( wait_time )
                sum_real_waits += ticks_diff( ticks_us(), t1 )
                sum_scheduled_waits += wait_time
                # could also add all wait_time, but that is different from ticks_diff.


                # Check jitter, wait_and_yield_usec tends to be longer than defined...
                # When wait times are small (<2msec), processing already takes that
                # time, so wait_and_yield_usec() is called with 0, and then
                # we already are late. For example, if 5 note on are done
                # at the same time, the second is late 2msec,  the third is late
                # 4msec, etc. Once a longer wait occurs, the timing
                # adjusts itself preserving the originally planned MIDI time.

                wtdiff = round((midi_time - ticks_diff(ticks_us(), playing_started_at))/1000)
                if wtdiff < -30:
                    ActuatorStats.count( "late notes")
                    ActuatorStats.max( "max note late", -wtdiff ) 
                elif wtdiff > 30:
                    # early notes
                    # Never seen early notes.
                    ActuatorStats.count( "early notes") 
                    ActuatorStats.max( "max note early",  wtdiff )
                
            # Turn one note on or off. Process program change
            self._process_midi(status, midi_event)

        total = ticks_diff(ticks_ms(),msec_start) 
        busy = total - sum_real_waits/1000
        self.logger.info(f"MIDI processing: {midi_events=}, msec/event={round(busy/midi_events, 1)}, busy={round(busy/total*100,1)}%, avg gc={scheduler.avg_gc_time} msec, late ratio={round((sum_real_waits/sum_scheduled_waits-1)*100,2)}%")
        # Without compression -d0, without track reduction
        # Start tuneid=iLDf7aZg6 '~wg2' tracks=4
        # MIDI processing: midi_events=1271, msec/event=3.6, busy=8.2%, avg gc=26 msec, late ratio=0.18%
        # Start tuneid=i9tN0C3Dt '~zorba polka rvb 1' tracks=7
        # MIDI processing: midi_events=12761, msec/event=1.0, busy=5.6%, avg gc=50 msec, late ratio=1.66%
        # Start tuneid=iSWeZDp89 '~QRS 60496 AlohaOe(1878) eRollMIDIWexp rvb 2' tracks=1
        # MIDI processing: midi_events=6164, msec/event=1.0, busy=4.5%, avg gc=50 msec, late ratio=0.64%
        # Start tuneid=iM3PgolP5 '~DC072 A022' tracks=4
        # MIDI processing: midi_events=4926, msec/event=1.1, busy=4.1%, avg gc=50 msec, late ratio=0.22%
        # Start tuneid=ie62Hpg_a '~TCHAIKOVSKY, Pyotr Ilyich  Chinese Dance , 'Nutcracker Suite' rvb 2' tracks=1
        # MIDI processing: midi_events=1522, msec/event=1.1, busy=2.8%, avg gc=48 msec, late ratio=0.66%
        # Start tuneid=i_idof11- '~wheels r1' tracks=10
        # MIDI processing: midi_events=6213, msec/event=2.0, busy=9.9%, avg gc=50 msec, late ratio=0.67%
        # Start tuneid=ieUQG4ya1 '~20 Mark Time March' tracks=1
        # MIDI processing: midi_events=3709, msec/event=1.0, busy=3.2%, avg gc=48 msec, late ratio=0.33%
        # Start tuneid=iCnBp3Dcw '~Carmela polka Juventino Rosas' tracks=1
        # MIDI processing: midi_events=3785, msec/event=1.0, busy=2.7%, avg gc=48 msec, late ratio=0.06%
        
        # Latest version March 2026, with track reduction and -d0 compression, ROMFS
        # Start tuneid=i9tN0C3Dt '~zorba polka rvb 1' tracks=7
        # MIDI processing: midi_events=12761, msec/event=1.1, busy=6.0%, avg gc=30 msec, late ratio=1.72%
        # Start tuneid=iSWeZDp89 '~QRS 60496 AlohaOe(1878) eRollMIDIWexp rvb 2' tracks=1
        # MIDI processing: midi_events=6164, msec/event=1.0, busy=4.7%, avg gc=30 msec, late ratio=2.34%
        # Start tuneid=iM3PgolP5 '~DC072 A022' tracks=4
        # MIDI processing: midi_events=4926, msec/event=1.2, busy=4.2%, avg gc=30 msec, late ratio=1.73%


    def _process_midi( self, status, midi_event ):
        try:
            # Prepare the parameters for the process_map call:
            # Channel, first data byte (value) and a notedef.
            channel = midi_event.channel
            value = midi_event.data[0]
        except:
            # Ignore if not a channel event.
            return

        # This will be useful for 99% of the cases, so let's do it here.
        curr_note = self.current_note
        curr_note.program_number = self.channelmap1[channel]
        # Value is note number for note on and note off events
        # Value is program number for program change events. 
        # Value is value of D0 event.
        curr_note.midi_number = value

        if status in self.process_map:
            self.process_map[status](channel, value, curr_note )

    def _program_change( self, channel, program, _ ):
        if channel != DRUM_CHANNEL:
            # Allow program change only for non-percussion channels
            # Internally program_number will be 1-128 for MIDI
            # to leave 0 for WILDCARD_PROGRAM and 129 for DRUM_PROGRAM
            self.channelmap1[channel] = program+1

    def processd0( self, _, value, notedef ):
        # Undo what compres_midi.py -d0 did to the note number
        if 0 <= value <= 63:
            notedef.midi_number = value+40
            controller.note_off( notedef )
        else:
            notedef.midi_number = value-24 # value-64+40
            controller.note_on( notedef )

    def get_progress(self):
        p = self.progress.get()
        p["playtime"] = self.time_played_us / 1000
        p["tempo_follows_crank"] = self.tempo_follows_crank
        p["repeats"] = self.repeats
        return p
    
    async def _calculate_tachometer_dt(self, midi_event_delta_us):
        # Recompute delta time due to crank or UI velocity setting
        additional_wait = 0
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


        # We get here if the crank is not turning and tempo_follows_crank is enabled.
        # Wait for the crank to start turning again and return the waiting time
        # to be added to the MIDI time delaying the rest of the tune.
        if not crank.is_turning() and crank.is_installed():
            # Let async tasks run freely while waiting
            scheduler.run_always()
            # And wait for the crank to turn

            additional_wait += await self._wait_for_crank_to_turn()
            # Resume scheduler, don't add a wait here
            await scheduler.wait_and_yield_usec(1)
            ActuatorStats.count("crank stop")

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

