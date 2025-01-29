# (c) 2023 Hermann Paul von Borries
# MIT License
# Handles response to notelist.html and note.html pages (tuning support)
from micropython import const
import os
import asyncio
from math import log10

if __name__ == "__main__":
    import sys
    sys.path.append("/software/mpy/")
# >>> tune to mean frequency vs. tune to 440.

from minilog import getLogger
from drehorgel import config, controller, actuator_bank, battery, microphone
import fileops
import frequency
import scheduler
import midi

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


class OrganTuner:
    def __init__(self):
        self.logger = getLogger(__name__)
        self._get_stored_tuning()
        self.tuner_queue = []
        self.start_tuner_event = asyncio.Event()
        self.organtuner_task = asyncio.create_task(self._organtuner_process())
        self.logger.debug("init ok")

    def queue_tuning(self, method, arg):
        scheduler.set_playback_mode(False)
        from drehorgel import setlist
        setlist.stop_tune()
        
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
        initial_tempo = (
            60  # Let's start with quarter notes in a largo at 60 bpm
        )
        fastest_note = 30  # 30 milliseconds seems to be a good lower limit on note duration
        play_during = 2000  # play during 2 seconds
        silence_percent = 10  # approximate percent of time assigned to a note
        minimum_silence = 30  # milliseconds, seems good limit
        tempo = initial_tempo
        while True:
            quarter = 60 / tempo * 1000
            if quarter < fastest_note:
                break
            note_duration = quarter * (1 - silence_percent / 100)
            silence = max(minimum_silence, quarter * silence_percent / 100)
            self.logger.debug(f"repeat note {note_duration=:.1f} {silence=:.1f}")
            t = 0
            while t <= play_during:
                # Queue notes, that makes repeat note interruptible
                self.queue_tuning( self.play_pin, ( pin_index, note_duration, silence) )
                t += note_duration + silence
            tempo *= 1.414  # double speed every 2
            self.queue_tuning( self.wait, 500 )

    async def all_pin_test(self, _):
        # Play all pìns

        pin_indexes = [ x for x in range(actuator_bank.get_pin_count())]
        pin_indexes.sort( key=lambda pi: actuator_bank.get_actuator_by_pin_index(pi).nominal_midi_note.midi_number or 9999)
        for duration in [240, 120, 60, 30]:  # In milliseconds
            for _ in range(2):
                # Play twice: one up, one down
                for pin_index in pin_indexes:
                    # Queue notes, that makes scale test interruptible
                    self.queue_tuning( self.play_pin, ( pin_index, duration, 50) )
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
                    self.queue_tuning( self.play_midi_note, ( midi_number, duration, 50) )
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
                                  default={},
                                  recreate=True)
        # Older versions use dict, delete that. 
        # If pin count is different, this organtuner.json is obsolete, delete.
        if (not isinstance( self.stored_tuning, list ) or 
            len(self.stored_tuning) != actuator_bank.get_pin_count()):
            self.stored_tuning = [ None for _ in range(actuator_bank.get_pin_count())]


        # Update stored tuning, if necessary
        for pin_index, actuator in enumerate(actuator_bank.get_all_pins()):
            d:dict = self.stored_tuning[pin_index] or  {
                    "centslist": [],
                    "amplist": [],
                    "amplistdb": []
                }
            # Update with current pin definition, just to be sure
            # it's up to date
            midi_note = actuator.nominal_midi_note
            d["name"] = str(midi_note)
            d["midi_number"] = midi_note.midi_number
            d["pinname"] = str(actuator) + " " + actuator.get_rank_name()
            d["frequency"] = round(actuator.nominal_midi_note.frequency(),1)
            self.stored_tuning[pin_index] = d

        fileops.write_json(
            self.stored_tuning, config.ORGANTUNER_JSON, keep_backup=False
        )
        return

    async def update_tuning(self, pin_index ):
        # Tune a single note and update organtuner.json
        self.logger.info(f"update_tuning {pin_index=}")
        # Get midi note to know nominal frequency
        actuator = actuator_bank.get_actuator_by_pin_index( pin_index )
        midi_note = actuator.nominal_midi_note
        # Do the tuning
        _, amp, freqlist, amplist = await self._get_note_pitch(
            pin_index, midi_note
        )
        # Update organtuner.json information
        d = self.stored_tuning[pin_index]
        d["centslist"] = [
            midi_note.cents(f) for f in freqlist
        ]
        d["amplist"] = amplist

        # Find the maximum amplitude of all note. That value sets 0 dB
        maxamp = 1
        for v in self.stored_tuning:
            for amp in v["amplist"]:
                if amp and amp > maxamp:
                    maxamp = amp
        # Now calculate all amplitudes in dB relative to maxamp
        for v in self.stored_tuning:
            # Calculate an average amplitude, convert to db
            avgamp = avg(v["amplist"])
            v["ampdb"] = self.calcdb(avgamp, maxamp)

            # Make a list of all amplitudes converted to db
            v["amplistdb"] = [self.calcdb(amp, maxamp) for amp in v["amplist"]]

            # If amp is None, the signal was too weak
            # Delete cents of weak signals
            for i in range(min(len(v["centslist"]), len(v["amplist"]))):
                if v["amplist"][i] is None:
                    v["centslist"][i] = None

            v["cents"] = avg(v["centslist"])

        fileops.write_json(
            self.stored_tuning, config.ORGANTUNER_JSON, keep_backup=False
        )

        self.logger.info(f"update_tuning {midi_note} stored in flash")

    def calcdb(self, amp, maxamp):
        if amp is not None and maxamp:
            dbval = 20 * log10(amp / maxamp)
            if dbval >= config.cfg["mic_signal_low"]:
                return dbval

    def set_to_mean_frequency(self):
        # >>> pending: set on web page
        # >>> ?Button "set to mean?" or "set to 440?"
        # >>> ?Button "Tune all to mean" "Tune all to 440"
        # >>> ???check boxes "Use mean frequency" or "Use 440"
        # >>> ???config.cfg["tune_to_mean"] = True
        # Set tuning frequency according to the mean deviation
        # of all notes. Zero deviation if no tuning available.
        cents_list = [ v["cents"] for v in self.stored_tuning if v ]
        try: 
            midi.set_tuning_frequency( sum( cents_list ) / len(cents_list) )
        except ZeroDivisionError:
            pass

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
                    ) = microphone.frequency( midi_note, store_this )
                except ValueError:
                    frequency = None
                    amplitude = 0
                    duration = 1
                    
                nominal = midi_note.frequency()
                # If too far away, ignore.
                if frequency and nominal*0.9 < frequency < nominal*1.1:
                    freqlist.append(frequency)
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

        except Exception as e:
            self.logger.exc(e, "Exception in _get_note_pitch")
        finally:
            actuator.off()

        if len(freqlist) == 0:
            return None, 0, freqlist, amplist

        frequency = avg( freqlist )
        amplitude = avg( amplist )
        return frequency, amplitude, freqlist, amplist

