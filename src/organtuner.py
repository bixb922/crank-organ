# (c) 2023 Hermann Paul von Borries
# MIT License
# Handles response to notelist.html and note.html pages (tuning support)

import os
import asyncio
from math import log10

if __name__ == "__main__":
    import sys
    sys.path.append("/software/mpy/")

from solenoid import solenoid
from minilog import getLogger
from config import config
import pinout
import midi
from battery import battery
import fileops
from microphone import microphone
import frequency

_TUNING_ITERATIONS = const(3)

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

    def queue_tuning(self, request):
        #  Request is a pair of action name ("tune", "note_on", "note_repeat")
        # and MIDI note number for "tune" and "note_on"
        # The queue is served by the _organtuner_process.
        self.tuner_queue.append(request)

        # Kick the process
        self.start_tuner_event.set()
        self.start_tuner_event.clear()

    def tune_all(self):
        self.queue_tuning(("wait",0))
        for midi_note in pinout.midinotes.get_all_valid_midis():
            self.queue_tuning(("tune", midi_note))

    async def sound_note(self, midi_note):
        for _ in range(8):
            # Sound 8 times for 1 second each time.
            solenoid.note_on(midi_note)
            await asyncio.sleep_ms(1000)
            solenoid.note_off(midi_note)
            await asyncio.sleep_ms(100)

    async def repeat_note(self, midi_note):
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
                solenoid.note_on(midi_note)
                await asyncio.sleep_ms(round(note_duration))
                solenoid.note_off(midi_note)
                await asyncio.sleep_ms(round(silence))
                t += note_duration + silence
            tempo *= 1.414  # double speed every 2
            await asyncio.sleep_ms(500)  # a bit of silence inbetween

    async def scale_test(self):
        # Make copy of official list to reverse/sort
        notelist = list(pinout.midinotes.get_all_valid_midis())
        notelist.sort(key=lambda m: m.hash)

        for duration in [240, 120, 60, 30]:  # In milliseconds
            for i in range(2):
                # Play twice: one up, one down
                for midi_note in notelist:
                    solenoid.note_on(midi_note)
                    await asyncio.sleep_ms(duration)
                    solenoid.note_off(midi_note)
                    await asyncio.sleep_ms(30)
                # alternate ascending and descending
                notelist.reverse()
            await asyncio.sleep_ms(500)

    def clear_tuning(self):
        try:
            os.remove(config.ORGANTUNER_JSON)
        except OSError:
            pass
        frequency.clear_stored_signals()
        # Recreate organtuner.json
        self._get_stored_tuning()
        self.logger.info("Stored tuning and stored signals removed")
    
    
    async def _organtuner_process(self):
        # Processes requests put into self.tuner_queue
        while True:
            try:
                if len(self.tuner_queue) > 0:
                    (request, midi_note) = self.tuner_queue.pop(0)
                    battery.end_heartbeat()

                    # Tuner queue can contain (request, integer hash)
                    # or (request, Note )
                    if isinstance(midi_note, int):
                        midi_note = midi.Note(byhash=midi_note)
                    if request == "tune":
                        # Tune all notes is implemented by queueing many
                        # individual tune requests
                        await self._update_tuning(midi_note)
                    elif request == "note_on":
                        await self.sound_note(midi_note)
                    elif request == "note_repeat":
                        await self.repeat_note(midi_note)
                    elif request == "scale_test":
                        await self.scale_test()
                    elif request == "wait":
                        await asyncio.sleep_ms( 1000 )
                    else:
                        raise RuntimeError(
                            f"Organtuner request unknown: {request}"
                        )
                else:
                    battery.start_heartbeat()

                    # Queue empty, wait to be woken up
                    await self.start_tuner_event.wait()
            except Exception as e:
                self.logger.exc(e, "exception in _organtuner_process")
            finally:
                pass

    def pinout_changed(self):
        self.clear_tuning()

    def stop_tuning(self):
        # Stop after processing current item
        self.tuner_queue = []

    def _get_stored_tuning(self):
        try:
            d = fileops.read_json(config.ORGANTUNER_JSON)
            # Keys are strings in json, but int needed here
            self.stored_tuning = dict((int(k), v) for k, v in d.items())

        except (OSError,ValueError):  
            # Make new organtuner_json file
            self.stored_tuning = {}
            for midi_note in pinout.midinotes.get_all_valid_midis():
                d = {}
                d["name"] = str(midi_note)
                d["centslist"] = []
                d["amplist"] = []
                d["amplistdb"] = []
                d["pinname"] = solenoid.get_pin_name(midi_note)
                self.stored_tuning[hash(midi_note)] = d
            fileops.write_json(
                self.stored_tuning, config.ORGANTUNER_JSON, keep_backup=False
            )

            self.logger.info(f"new {config.ORGANTUNER_JSON} written")
        return

    async def _update_tuning(self, midi_note):
        # Tune a single note and update organtuner.json
        self.logger.info(f"_update_tuning {midi_note}")

        freq, amp, freqlist, amplist = await self._get_note_pitch(
            midi_note
        )

        h = hash(midi_note)
        self.stored_tuning[h]["centslist"] = [
            midi_note.cents(f) for f in freqlist
        ]
        self.stored_tuning[h]["amplist"] = amplist

        # Find the maximum amplitude, that sets 0 dB
        maxamp = 1
        for v in self.stored_tuning.values():
            for amp in v["amplist"]:
                if amp and amp > maxamp:
                    maxamp = amp
        # Now calculate all amplitudes in dB relative to maxamp
        for v in self.stored_tuning.values():
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

        self.logger.info(f"_update_tuning {midi_note} stored in flash")

    def calcdb(self, amp, maxamp):
        if amp is not None and maxamp:
            dbval = 20 * log10(amp / maxamp)
            if dbval >= config.cfg["mic_signal_low"]:
                return dbval

            
    async def _get_note_pitch(self, midi_note):
        store_signal = config.cfg.get("mic_store_signal", False)
        freqlist = []
        amplist = []
        solenoid.note_on(midi_note)
        # Wait for sound to stabilize before calling tuner
        await asyncio.sleep_ms(300)
        try:
            for iteration in range(_TUNING_ITERATIONS):
                store_this = (store_signal and iteration==0)
                # Save signal only for iteration 0
                try:
                    (
                        frequency,
                        amplitude,
                        duration,
                    ) = microphone.frequency(midi_note, store_this)
                except ValueError:
                    frequency = None
                    amplitude = 0
                    duration = 1
                    
                nominal = midi_note.frequency()
                if frequency and nominal*0.97 < frequency < nominal*1.03:
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
                await asyncio.sleep_ms(10)  # yield, previous code was CPU bound
            # Store last sample in flash

        except Exception as e:
            self.logger.exc(e, "Exception in _get_note_pitch")
        finally:
            solenoid.note_off(midi_note)

        if len(freqlist) == 0:
            return None, 0, freqlist, amplist

        frequency = avg( freqlist )
        amplitude = avg( amplist )
        return frequency, amplitude, freqlist, amplist


organtuner = OrganTuner()
