# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# Handles response to notelist.html and note.html pages (tuning support)
from micropython import const
import os
import asyncio
from math import log10
import time

if __name__ == "__main__":
    import sys
    sys.path.append("/software/mpy/")

from minilog import getLogger
from drehorgel import config, controller, actuator_bank, battery
import fileops
import frequency
import midi

from microphone import Microphone
    


# Time spent for measuring frequency for each note
_TARGET_DURATION = 0.8 # seconds
# But never less than this number of frequency measurements:
_MINIMUM_MEASUREMENTS = const(3)

def avg(lst):
    n = 0
    sumval = 0
    for val in lst:
        if val is not None:
            sumval += val
            n += 1
    if n > 0:
        return sumval / n
    # Return none if no values in list

# OrganTuner acts as singleton, it is instantiated on demand by webserver.py
# That saves some time at startup and saves 85 kb of memory until needed,
# reducing garbage collection time from 58 to 38 msec. 
# It also saves about 2 seconds at startup time.
# As of June 1, 2025, boot time is 4100ms, memory 231,000 kb, gc time 38 msec (when idle)
# After loading organtuner and friends, memory 326,000 kb gc time 52 msec (when idle)
class OrganTuner:
    def __init__(self, microphone_pin ):
        self.logger = getLogger(__name__)
        self._get_stored_tuning()
        self.tuner_queue = []
        self.start_tuner_event = asyncio.Event()
        self.organtuner_task = asyncio.create_task(self._organtuner_process())
        self.microphone = Microphone( microphone_pin, config.cfg["mic_test_mode"] )
        # Each pair is (note_duration, silence) in milliseconds
        # note durataions get halved every two repeats
                # Organ roll specifications have a hole size of 2 to 3 mm
        # and advance at a speed of 4 to 6 cm per second.
        # This means that a hole takes about 45 milliseconds end-to-end
        # although the hole opens gradually...
        # I'll use that as the shortest slence too
        # Analyzing organ MIDI files gives these approximate values:
        #    40-50 ms note length approximate minimum
        #    50-60 ms silence approximate minimum
        # On piano, the fastest single note repeat is 14 notes/minute
        # = one note every 70 msec
        # On trumpet, a fast single note repeat is sixteemnth notes at
        # 160 bpm = 90 msec per note. Double tonguing is faster but not double...
        self.repeat_times = [(850,150),(601,106), (425,75), (301,53), (213,50), (150,50), (106,50), (75,50), (53,50), (40,50), (30,50), (30,40), (30, 30)]

        self.logger.debug("init ok")

    def get_stats( self ):
        # Need calculated fields for stats
        tuning = self._calculate_tuning()
        # Get global cents and frequency data using info of ALL notes
        cents_list = [ v["cents"] for v in tuning if v and "cents" in v and v["cents"] is not None]
        avg_frequency = avg( v["measured_freq"]/v["frequency"] for v in tuning if v and "measured_freq" in v and v["measured_freq"] is not None )
        if avg_frequency:
            avg_frequency = round(avg_frequency*midi.tuning_frequency,1)
        else:
            avg_frequency = "?"
        tuning_cents = midi.tuning_cents # midi module has the maximum deviation allowed, set by configuration.
        tuned = len(cents_list)
        tuned_ok = sum( 1 for c in cents_list if abs(c) <= tuning_cents )
        all_notes = len(tuning)
        return {
                "tuned_ok": tuned_ok,
                "tuned_not_ok": tuned - tuned_ok,
                "not_tested": all_notes - tuned,
                "pins": all_notes, 
                "avg_frequency": avg_frequency,
                "tuning_frequency": midi.tuning_frequency,
                "tuning_cents": tuning_cents }

    def queue_tuning(self, method, arg):
        from drehorgel import setlist
        setlist.stop_playback()
        
        #  Request is a tuple of an (async organtuner method,
        # and an argument). Normally the argument is a pin_index but can
        # also be a tuple depending on the method called
        # The queue is served by the _organtuner_process.
        self.tuner_queue.append( (method, arg) )
    
        # Kick the process
        self.start_tuner_event.set()
        self.start_tuner_event.clear()

    def tune_all(self):
        self.queue_tuning( self.wait, 1000 )
        # Open all defined pins, bypass registers
        for pin_index in range(actuator_bank.get_pin_count()):
            self.queue_tuning( self.update_tuning, pin_index )

    async def sound_note(self, pin_index ):
        # Sound 8 times for 1 second each time.
        for _ in range(8):
            self.queue_tuning( self.play_pin, ( pin_index, 1000, 100) )

    async def repeat_note(self, pin_index ):
        for note_duration, silence in self.repeat_times:
            # Queue repeat, don't queue play_pin(), thus repeat is not interruptible but more precise
            self.queue_tuning( self.repeat_pin, ( pin_index, note_duration, silence) )

    def get_repeat_times(self):
        return " ".join( f"{note_duration}/{silence}" for note_duration, silence in self.repeat_times )

    async def repeat_pin( self, arg ):
        pin_index, duration, silence = arg
        # Repeat notes for 4 seconds
        actuator = actuator_bank.get_actuator_by_pin_index( pin_index )
        play_during = 4000 # milliseconds
        self.logger.debug(f"repeat note {duration=} {silence=}")
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < play_during:
            actuator.on()
            # time.sleep_us() is precise (but blocks asyncio loop)
            time.sleep_us( duration * 1000  )
            actuator.off()
            time.sleep_us( silence * 1000 ) 
        # Let queued async task do their job now, and leave a bit of
        # silence before the next note
        await asyncio.sleep_ms(500)
 

    async def all_pin_test(self, _):
        # Play all pìns

        pin_indexes = [ x for x in range(actuator_bank.get_pin_count())]
        pin_indexes.sort( key=lambda pi: actuator_bank.get_actuator_by_pin_index(pi).nominal_midi_note.midi_number or 9999)
        for duration in [240, 120, 60, 30]:  # In milliseconds
            for _ in range(2):
                # Play twice: one up, one down
                for pin_index in pin_indexes:
                    # Queue notes, that makes scale test interruptible
                    self.queue_tuning( self.play_pin, ( pin_index, duration, 100) )
                # alternate ascending and descending
                pin_indexes.reverse()
            await asyncio.sleep_ms(500)

    async def scale_test(self, _):
        # Play all notes. Unknown notes will play in zero time,
        # so they are essentially skipped. This is because 
        # controller.note_on() will return falsish if no
        # note was found, so play_midi_note skips waiting and
        # skips note off.
        notelist =[ midi_number for midi_number in range(128)]
        for duration in [700, 240, 120, 60, 30]:  # In milliseconds
            for _ in range(2):
                # Play twice: one up, one down
                for midi_number in notelist:
                    # Queue notes, that makes scale test interruptible
                    self.queue_tuning( self.play_midi_note, ( midi_number, duration, 100) )
                # alternate ascending and descending
                notelist.reverse()
            await asyncio.sleep_ms(500)

    async def play_pin( self, arg ):
        #  Make a pipe sound
        pin_index, duration, silence = arg
        actuator = actuator_bank.get_actuator_by_pin_index( pin_index )
        actuator.on()
        await asyncio.sleep_ms(round(duration))
        actuator.off()
        await asyncio.sleep_ms(round(silence))

    async def play_midi_note( self, arg ):
        #  Make a midi note sound
        midi_number, duration, silence = arg
        # Play program_number=1 (piano), that should
        # work for most "nominal" midi note definitios
        # except drums.
        # controller.note_on will return falsish if 
        # no note was found. If so, skip waiting and note_off.
        if controller.note_on(  1,  midi_number ):
            await asyncio.sleep_ms(round(duration))
            controller.note_off( 1, midi_number)
            await asyncio.sleep_ms(round(silence))

    def clear_tuning(self):
        try:
            os.remove(config.ORGANTUNER_JSON)
        except OSError:
            pass
        frequency.clear_stored_signals()
        # Recreate organtuner.json
        self._get_stored_tuning()
        # Get the tuning frequency according to configuration

        self.logger.info("Stored tuning and stored signals removed")
    
    async def wait( self, duration ):
        await asyncio.sleep_ms( duration )

    async def _organtuner_process(self):
        # Processes requests put into self.tuner_queue
        while True:
            try:
                if len(self.tuner_queue) > 0:
                    request = self.tuner_queue.pop(0)
                    battery.end_heartbeat()

                    # Tuner queue request is a tuple of the form
                    # ( async method, arg )
                    await request[0]( request[1] )
                else:
                    battery.start_heartbeat()

                    # Queue empty, wait to be woken up
                    await self.start_tuner_event.wait() # type:ignore
            except Exception as e:
                self.logger.exc(e, "exception in _organtuner_process")
            finally:
                pass
            
    def stop_tuning(self):
        # Stop after processing current item
        self.tuner_queue = []


    def _get_stored_tuning(self):
        self.stored_tuning:list = fileops.read_json(config.ORGANTUNER_JSON,
                                    default=[],
                                    recreate=True)
        # Older versions used dict, delete that format of the organtuner.json. 
        # Also: if pin count is different, this organtuner.json is obsolete, delete.
        if (not isinstance( self.stored_tuning, list ) or 
            len(self.stored_tuning) != actuator_bank.get_pin_count()):
            self.stored_tuning = [{}]*actuator_bank.get_pin_count()

        # Update stored tuning, if necessary
        changed = False
        # Delete surplus keys of older versions of this software.
        for v in self.stored_tuning:
                for k in ("cents", "centslist", "centlists", "measured_freq", "frequency", "ampdb", "amplistdb"):
                    if k in v:
                        del v[k]
                        changed = True
                        
        for pin_index, actuator in enumerate(actuator_bank.get_all_pins()):
            # Make a copy to see if there was a change
            v:dict =  dict(self.stored_tuning[pin_index] )
            # Update with current pin definition, just to be sure
            # it's up to date
            midi_note = actuator.nominal_midi_note
            # Keep redundant info about notes to check if pinout
            # changes and update accordingly.
            # "name" is for example "C3(48)"
            # "pinname" is for example "MIDISerial(10,).48 "
            v["name"] = str(midi_note)
            v["midi_number"] = midi_note.midi_number
            v["program_number"] = midi_note.program_number 
            if not midi_note.program_number:
                # save some space. Don't save 0 or null or space if wildcard program number
                del v["program_number"]

            v["pinname"] = str(actuator) + " " + actuator.get_rank_name()
            a = self.stored_tuning[pin_index]
            if not a or a["name"]!=v["name"] or a["pinname"]!=v["pinname"] or a["midi_number"]!=v["midi_number"]:
                v["amplist"] = []
                v["freqlist"] = []
                self.stored_tuning[pin_index] = v
                changed = True
        if changed:
                fileops.write_json(
                    self.stored_tuning, config.ORGANTUNER_JSON, keep_backup=False
                )
        return

    async def update_tuning(self, pin_index ):

        # Tune a single note and update organtuner.json
        # Get midi note to know nominal frequency
        actuator = actuator_bank.get_actuator_by_pin_index( pin_index )
        midi_note = actuator.nominal_midi_note
        self.logger.info(f"start update_tuning {actuator=} {midi_note=}")
        # Do the tuning. Don't need average frequency and amplitude
        _, _, freqlist, amplist = await self._get_note_pitch(
            pin_index, midi_note
        )
        # Update organtuner.json information
        d = self.stored_tuning[pin_index]
        d["amplist"] = amplist
        d["freqlist"] = freqlist
        fileops.write_json(
            self.stored_tuning, config.ORGANTUNER_JSON, keep_backup=False
        )
        self.logger.info(f"completed update_tuning {actuator=} {midi_note=} stored in flash")

    def calcdb(self, amp, maxamp):
        if amp is not None and maxamp:
            dbval = 20 * log10(amp / maxamp)
            if dbval >= config.cfg["mic_signal_low"]:
                return dbval


    async def _get_note_pitch(self, pin_index, midi_note):
        store_signal = config.cfg.get("mic_store_signal", False)
        freqlist = []
        amplist = []
        actuator = actuator_bank.get_actuator_by_pin_index( pin_index )
        actuator.on()
        # Wait for sound to stabilize before calling tuner
        await asyncio.sleep_ms(300)
        try:
            sum_durations = 0
            iteration = 0
            # Measure during _TARGET_DURATION but not less than _MINIMUM_MEASUREMENTS times
            while sum_durations <= _TARGET_DURATION or iteration < _MINIMUM_MEASUREMENTS:
                # Store the first signal, if config says so
                store_this = (store_signal and iteration==0)
                # Save signal only for iteration 0
                try:
                    ( frequency, amplitude, duration,
                    ) = self.microphone.frequency( midi_note, store_this )
                except ValueError:
                    frequency = None
                    amplitude = None
                    duration = 1
                # Configuration option mic_amplitude is True means
                # that the amplitude is measured and stored.
                if not config.cfg.get("mic_amplitude", False):
                    amplitude = None 
                nominal = midi_note.frequency()
                # If too far away, ignore.
                if frequency and nominal*0.9 < frequency < nominal*1.1:
                    freqlist.append(frequency)
                    if amplitude is not None:
                        # Convert to dB
                        amplitude = 20 * log10(amplitude)
                        amplist.append(amplitude)
                    # Show tuning
                    cents = midi_note.cents(frequency)
                    print(
                        f"_get_note_pitch iteration {iteration=} {midi_note=} {nominal=:.1f}Hz measured={frequency:.1f}Hz {cents=:.1f} {amplitude=}"
                    )
                else:
                    print(
                        f"_get_note_pitch iteration {iteration}  {midi_note=} no frequency could be measured, {frequency=} {amplitude=}"
                    )
                sum_durations += duration
                iteration += 1
                await asyncio.sleep_ms(10)  # yield, previous code was CPU bound
            # Store last sample in flash
            self.microphone.save_hires_signal(midi_note)
        except Exception as e:
            self.logger.exc(e, "Exception in _get_note_pitch")
        finally:
            actuator.off()

        if len(freqlist) == 0:
            return None, 0, freqlist, amplist

        frequency = avg( freqlist )
        amplitude = avg( amplist )
        return frequency, amplitude, freqlist, amplist

    def get_organtuner_json( self ):
        # Return updated tuning to the browser.
        # The browser does not fetch organtuner.json
        return self._calculate_tuning()
    
    def _calculate_tuning(self):
        # Do calculated fields here:
        #  ampdb, amplistdb, cents, centslist
        # The calculated fields are done on the fly when
        # browser asks for values. 
        # Calculated fields are not stored, they depend on too many variables.
        # Make a deep copy of stored_tuning, so the stored_tuning remains small.
        tuning = list( dict(v) for v in self.stored_tuning )
        # Find the global maximum amplitude of all notes. That value sets 0 dB
        maxamp = 1
        for v in tuning:
            for amp in v["amplist"]:
                if amp is None:
                    self.logger.info(f"Amplitude must be != None {amp=} {v=}")
                if amp and amp > maxamp:
                    maxamp = amp

        for v in tuning:
            # Reconstruct a NoteDef for the MIDI note to get frequency, cents, tuning
            midi_note = midi.NoteDef(v.get("program_number",0), v["midi_number"])
            
            # Calculate frequency (adjusted by tuning frequency)
            # and use that to calculate cents
            v["frequency"] = midi_note.frequency()
            freqlist = v.setdefault("freqlist", [])
            centslist = [ midi_note.cents(f) for f in freqlist ]
            v["measured_freq"] = avg(freqlist)

            # Calculate an average amplitude, convert to db
            amplist = v.setdefault("amplist", [])
            avgamp = avg(amplist)
            v["ampdb"] = self.calcdb(avgamp, maxamp)

            # Make a list of all amplitudes converted to db
            v["amplistdb"] = [self.calcdb(amp, maxamp) for amp in amplist]

            v["cents"] = avg(centslist)
            v["centslist"] = centslist
        # Calculated values are not stored
        return tuning