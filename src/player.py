# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License


# Plays MIDI files using the umidiparser module
from micropython import const
from time import ticks_us, ticks_diff, ticks_ms, ticks_add
import asyncio
from random import getrandbits

from minilog import getLogger
from drehorgel import tunemanager, controller, battery, history, crank, config, timezone

import scheduler
from fileops import open_midi
from actuatorstats import ActuatorStats

_CANCELLED = const("cancelled") 
_ENDED = const("ended")
_PLAYING = const("playing")

_START_DELAY = const(50) # 50 msec delay before first note to process MIDi events at start of file

class MIDIPlayerProgress:
    def __init__(self):
        self.boot_session = hex(getrandbits(24))
        self.progress = {"tune": None, "playtime": 0, "status": ""}

    def tune_started(self, tuneid):
        self.progress = {"tune": tuneid, "playtime": 0, "status": _PLAYING}

    def tune_ended(self):
        self.progress["status"] = _ENDED

    def tune_cancelled(self):
        self.progress = {"tune": None, "playtime": 0, "status": _CANCELLED}

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
        
        # Put some initial values here, will be replaced before waiting for a tune
        self.tempo_follows_crank = config.tempo_follows_crank
        self.repeats_requested = 1
        self.started_by_crank = crank.is_installed()
        self.repeat_count = 0

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
        await scheduler.wait_ms( 30 ) # must be be > _RESERVED_MS

        # Assign variables here so finally: does not fail for "local variable referenced before assignment"
        self.time_played_us = 0
        start_time = timezone.now_timestamp()
        midi_fn = None
        duration = 1 
        title = None
        self.repeat_count = 0
        # don't reset repeats_requested here, could have been
        # incremented while waiting for tune to startd. Reset repeats_requested
        # after tune stops.
        midifile = None
        
        try:
            battery.end_heartbeat()
            # get_info_by_id() could fail in case tunelib
            # has not been correctly updated. 
            midi_fn, duration, title = tunemanager.get_info_by_tuneid(tuneid)
            if not midi_fn:
                # tuneid not in tunelib. Could be reported better in history
                # or shown in play page?
                raise ValueError(f"{tuneid} not found in tunelib or file not found")
            # Get MidiFile object
            midifile = open_midi( midi_fn ) # fileops.open_midi

            self.logger.info(f"Start {tuneid=} '{title}' tracks={len(midifile.tracks)} type={midifile.format_type}" )
            controller.all_notes_off()
            ActuatorStats.zero()
            # From play_tune from tunemanager to _play = 150 msec
            # In "barrel organ mode", repeat until
            # user presses button to get to next tune.
            
            while self.repeat_count < self.repeats_requested:
                self.repeat_count += 1
                controller.file_start( midifile ) # may raise exception
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
                                self.time_played_us, 
                                duration,
                                self.repeat_count )
            
            self.tempo_follows_crank = config.tempo_follows_crank
            self.repeats_requested = 1
            self.repeat_count = 0

            # scheduler.fdump() # for debug 
            
    def _insert_history(self, tuneid, start_time, time_played_us, duration, repeat_count ):
        try:
            percentage_played = round(time_played_us / 1_000 / duration * 100)
        except ZeroDivisionError:
            percentage_played = 0
        history.add_entry(tuneid, start_time, percentage_played, repeat_count )
        
        # Now done in the browser:
        #if percentage_played > 95:
        #    tunemanager.add_one_to_history( tuneid )

    async def _play(self, midifile ):
        # Sum of delta_us without tachometer/crank stop adjust, used for % played.
        self.time_played_us = 0  
        # start_ticks: The time when the tune started playing
        # origin_ticks: Origin of time for MIDI calculations. Leave some time to process possible events previous
        # to start of music. This can be important if there are
        # a lot of meta events with long texts before the first note.
        # There are cases with 100 program changes + control changes and other
        # crowded MIDI files.
        # 50 msec should be enough,
        # This should not be an issue for MIDI files compressed with
        # compress_midi.py, since all meta events have been stripped.
        start_ticks = ticks_ms() 
        origin_ticks = ticks_add( start_ticks, _START_DELAY )
        # Tally MIDI time in usec. delta_us is already in usec, so we don't loose precision.
        # If MIDI time was in msec, each delta_us//1000 added would loose 0.5 msec
        # as a systematic (not random) error.
        # With 10_000 events, that is a big error. So midi_time_us and delta_us must be in usec.
        # Same reasoning applies to self.time_played_us.
        midi_time_us = 0
        sum_real_waits_ms = 0
        sum_scheduled_waits_ms = 0
        controller_us = 0

        for midi_event in midifile:
            ActuatorStats.count("midi events")
            if midi_event.is_channel() and midi_event.channel == 9:
                ActuatorStats.count("ch10 events")

            # time_played_us goes from 0 to the length of the midi file in microseconds
            # and is not affected by playback speed. Is used to calculate
            # % of tune played.
            self.time_played_us += midi_event.delta_us # type:ignore

            # An optimization. For example, often there are many control changes
            # (up to 100)
            # with 0 delta time. Skip these to avoid delays.
            if midi_event.delta_us == 0 and not controller.must_process(midi_event):
                continue
            
            # midi_time_us is the calculated time since the start of the MIDI file
            # considering all midi_event.delta_us plus the effect of the crank
            # (e.g. crank stops and crank velocity). 
            # Without tachometer it would be: midi_time_us += midi_event.delta_us    
            midi_time_us += await self._calculate_tachometer_us( midi_event.delta_us )

            # playing_time_us is the wall clock time since playing started
            # Use ticks_diff(ticks_ms) to allow for times > 8.9 minutes, since ticks_us wraps around 
            playing_time_us = ticks_diff(ticks_ms(), origin_ticks)*1_000

            # Wait for the difference between the "time that is" and 
            # the "time that should be"
            wait_time_ms = (midi_time_us - playing_time_us + 500) // 1000
            if wait_time_ms > 3:
                # _process_midi() takes about 1.5 msec,
                # no need to process scheduler.wait_ms() for that.
                # Worst case: this note may be a bit early.
                # Best case: next notes will be on time if delta_us is small or zero

                # Sleep until scheduled time has elapsed
                t1 = ticks_ms()
                await scheduler.wait_ms(wait_time_ms)
                sum_real_waits_ms += ticks_diff( ticks_ms(), t1 )
                sum_scheduled_waits_ms += wait_time_ms

                # Check jitter, wait_ms)= tends to run longer than requested.
                # When wait times are small (<2msec), processing already takes that
                # time, so wait_ms() is called with 0, and then
                # we already are late. For example, if 5 note on are done
                # at the same time, the second is late 2msec,  the third is late
                # 4msec, etc. Once a longer wait occurs, the timing
                # adjusts itself preserving the originally planned MIDI time.

                wtdiff_ms = (midi_time_us - ticks_diff(ticks_ms(), origin_ticks)*1_000 + 500)//1_000
                if wtdiff_ms < -20:
                    ActuatorStats.count( "late notes")
                    ActuatorStats.max( "max note late", -wtdiff_ms ) 
                elif wtdiff_ms > 20:
                    # early notes
                    # Never seen early notes.
                    ActuatorStats.count( "early notes") 
                    ActuatorStats.max( "max note early",  wtdiff_ms )
            t2 = ticks_us()
            controller.process_midi( midi_event )
            controller_us += ticks_diff(ticks_us(), t2)

        total_ms = ticks_diff(ticks_ms(),start_ticks) 
        busy_ms = total_ms - sum_real_waits_ms
        midi_events = ActuatorStats.get()["midi events"]
        if midi_events > 0:
            self.logger.info(f"MIDI processing: msec/event={busy_ms/midi_events:.2f}, busy={busy_ms/total_ms*100:.1f}%, avg gc={scheduler.avg_gc_time} msec, late ratio={(sum_real_waits_ms/(sum_scheduled_waits_ms)-1)*100:.2f}% {self.repeat_count=} controller={controller_us/1_000/midi_events:.2f} msec/event")    

        # Without compression, without -d0, without track reduction
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
        
        # March 2026, with track reduction and -d0 compression, ROMFS
        # Start tuneid=i9tN0C3Dt '~zorba polka rvb 1' tracks=7
        # MIDI processing: midi_events=12761, msec/event=1.1, busy=6.0%, avg gc=30 msec, late ratio=1.72%
        # Start tuneid=iSWeZDp89 '~QRS 60496 AlohaOe(1878) eRollMIDIWexp rvb 2' tracks=1
        # MIDI processing: midi_events=6164, msec/event=1.0, busy=4.7%, avg gc=30 msec, late ratio=2.34%
        # Start tuneid=iM3PgolP5 '~DC072 A022' tracks=4
        # MIDI processing: midi_events=4926, msec/event=1.2, busy=4.2%, avg gc=30 msec, late ratio=1.73%

        # June 2026, after refactoring midicontroller/player, better track reduction in compress_midi
        # track reduction, -d0 compression, 20 note scale
        # Start tuneid=iM3PgolP5 '~DC072 A022' tracks=1
        # MIDI processing: midi_events=4702, msec/event=0.3, busy=1.1%, avg gc=20 msec, late ratio=1.66% self.repeat_count=1
        # track reduction, -d0 compression, 40 note RC/PWM with PCAs connected
        # Start tuneid=iM3PgolP5 '~DC072 A022' tracks=1
        # MIDI processing: midi_events=4702, msec/event=0.3, busy=1.1%, avg gc=24 msec, late ratio=1.8% self.repeat_count=1
        # Start tuneid=i9tN0C3Dt '~zorba polka rvb 1' tracks=2
        # MIDI processing: midi_events=7926, msec/event=0.5, busy=1.6%, avg gc=24 msec, late ratio=1.51% self.repeat_count=1
        # Start tuneid=i_idof11- '~wheels r1' tracks=1
        # MIDI processing: midi_events=4798, msec/event=0.3, busy=1.3%, avg gc=28 msec, late ratio=2.4% self.repeat_count=1
        # Uncompressed file:
        # Start tuneid=iLDf7aZg6 '~wg2' tracks=4
        # MIDI processing: midi_events=1271, msec/event=3.7, busy=8.6%, avg gc=28 msec, late ratio=0.74% self.repeat_count=1
        # 64 note midi serial
        # Start tuneid=iM3PgolP5 '~DC072 A022' tracks=1
        # serial, 64 notes defined, no passthrough
        # MIDI processing: midi_events=4702, msec/event=0.3, busy=1.2%, avg gc=22 msec, late ratio=1.68% self.repeat_count=1
        # serial, 64 notes defined, passthrough
        # MIDI processing: midi_events=4702, msec/event=0.3, busy=1.2%, avg gc=22 msec, late ratio=1.48% self.repeat_count=1
        # serial, 0 notes defined, passthrough
        # MIDI processing: midi_events=4702, msec/event=0.6, busy=2.0%, avg gc=20 msec, late ratio=1.69% self.repeat_count=1

        # After adding reserved time to scheduler:
        # Start tuneid=iM3PgolP5 '~DC072 A022' tracks=1 type=208
        # MIDI processing: midi_events=4922, msec/event=0.95, busy=3.4%, avg gc=24 msec, late ratio=0.31% self.repeat_count=1 controller=0.66 msec/event
        # Actuator stats: note on=1731, note not found=729, max polyphony=7
        # Grease has drum notes.
        # Start tuneid=iedTbEvZJ '~grease' tracks=10 type=208
        # MIDI processing: midi_events=3120, msec/event=4.89, busy=21.0%, avg gc=26 msec, late ratio=0.26% self.repeat_count=1 controller=4.49 msec/event
        # End tuneid=iedTbEvZJ '~grease' midi_fn=/data/midi_cached.mid, played 72.52s of 72.52s
        # Actuator stats: note on=982, note not found=573, max polyphony=8
        # Same with 2 tracks:
        # Start tuneid=iedTbEvZJ '~grease' tracks=2 type=208
        # MIDI processing: midi_events=3112, msec/event=4.96, busy=21.3%, avg gc=28 msec, late ratio=0.19% self.repeat_count=1 controller=4.57 msec/event
        # End tuneid=iedTbEvZJ '~grease' midi_fn=/data/midi_cached.mid, played 72.52s of 72.52s
        # Actuator stats: note on=982, note not found=573, max polyphony=8

    def get_progress(self):
        progress = self.progress.get()
        progress["playtime"] = self.time_played_us / 1_000
        progress["tempo_follows_crank"] = self.tempo_follows_crank 
        # Repeats requested are transient, don't survive power down.
        progress["repeats_requested"] = self.repeats_requested 
        progress["repeats_count"] = self.repeat_count
        return progress
    


    async def _calculate_tachometer_us(self, midi_event_delta_us):
        # Readjust delta time due to crank or UI velocity setting

        # Wait for the crank to start turning again and return the waiting time
        # to be added to the MIDI time delaying the rest of the tune.
        if self.started_by_crank and not crank.is_turning(): 
            # Music stops when crank stops. This does not depend on
            # "tempo_follows_crank", but needs crank installed and
            # tune started by crank.
            # Let async tasks run freely while waiting
            # Use ticks_ms instead of ticks_us, to allow for times > 8.9 minutes
            start_wait_ms = ticks_ms()
            scheduler.run_always()
            self.logger.debug("waiting for crank to turn")
            # Don't let a note on during wait, it may
            # be realistic but it's not nice
            controller.all_notes_off()
            # Wait for the crank to start turning
            await crank.wait_start_turning()

            # Now the crank is turning again. Resume scheduler
            await scheduler.wait_ms(1)
    
            ActuatorStats.count("crank stop")
            # Use wait time as MIDI time. midi_event_delta_us disappears.
            # Return time converted to usec
            return ticks_diff(ticks_ms(), start_wait_ms)*1_000

        # Change playback speed with UI settings.
        # Change playback speed with crank rpsec if:
        #   crank sensor is enabled
        #   AND user selected "tempo follows crank"
        #   AND started by crank. 
        # Otherwise, only UI influences tempo.
        normalized_vel = crank.get_normalized_rpsec(self.tempo_follows_crank and self.started_by_crank)
        if normalized_vel < 0.1:
            # Avoid division by zero.
            # Also a very slow speed is meaningless here, 
            # crank should have signaled that it has stopped...
            normalized_vel = 1
        return round(midi_event_delta_us / normalized_vel)
    

    def set_tempo_follows_crank( self, v ):
        # set by webserver
        # Can override config but cannot override if not started by crank
        self.tempo_follows_crank = v and crank.is_installed() and self.started_by_crank

    def change_repeats_requested( self, v ):
        # called by webserver,with v +1 or -1
        self.repeats_requested = max( 1, self.repeats_requested + v )
      
    def set_started_by_crank( self, v ):
        # False if crank not installed
        # False if started by touchpad or web start button
        # True if crank installed and started by crank turning
        self.started_by_crank = v and crank.is_installed()
        
        # Can't use  "tempo follows crank" if tune not started by crank
        self.tempo_follows_crank = self.tempo_follows_crank and self.started_by_crank
