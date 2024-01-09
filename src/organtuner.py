# (c) 2023 Hermann Paul von Borries
# MIT License
# Handles response to notelist.html and note.html pages (tuning support)


import os
import array
from time import ticks_ms, ticks_diff, ticks_us
import gc
import asyncio
from machine import Pin, ADC
from math import sin, log10
import random

import zcr
from solenoid import solenoid
from minilog import getLogger
from config import config
import pinout
import midi
from battery import battery
import fileops

# >>> PIN NUMBER - ADD TO ORGANTUNER.JSON to stabilize for changes?

# Sample rate is about 35kHz for a ESP32-S3 at 240Mhz
# so 2000 samples is about 55 msec of data
# of data.
_BUFFER_SIZE = const(2048)

_TUNING_ITERATIONS = const(3)
_logger = getLogger(__name__)


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


class Signal:
    def __init__(self):
        # Allocate memory as a first step to ensure availability
        gc.collect()
        self.adc_signal = array.array("i", (0 for _ in range(_BUFFER_SIZE)))
        self.auto_signal = array.array("f", self.adc_signal)

        if pinout.gpio.microphone_pin and not config.cfg["mic_test_mode"]:
            self.adc_device = ADC(
                Pin(pinout.gpio.microphone_pin, Pin.IN), atten=ADC.ATTN_11DB
            )
            _logger.debug("Microphone ADC configured")
        else:
            _logger.debug(
                "No microphone, test mode= {config.cfg['mic_test_mode']}"
            )
            self.adc_device = None

        self.do_autocorrelation = True
        self._test_performance()

    def _test_performance(self):
        # Tune one note, measure timings and calculate limits of this tuning.
        midi_note = pinout.midinotes.get_random_midi_note()
        t0 = ticks_ms()
        freq, amplitude, duration = self._sample_normalize_filter_zcr(midi_note)
        dt = ticks_diff(ticks_ms(), t0) / 1000 - duration
        samples_per_sec = 1 / duration * len(self.adc_signal)
        _logger.debug(
            f"Performance test done {duration=} {_TUNING_ITERATIONS=} {samples_per_sec=} processing {dt:.2f} sec"
        )
        # At least 5 cycles in buffer for autocorrelation to make sense
        # Max frequency very safely below Nyquist = sample rate/2, but to leave
        #  margin: samples_per_sec/4 means 4 samples at least per cycle
        _logger.debug(f"Frequency from {1/(duration/5)} to {samples_per_sec/4}")

    @micropython.native
    def _sample_adc(self, midi_note):
        gc.collect()
        n = len(self.adc_signal)
        if self.adc_device:
            # Sample the mic. Should read about 30.000 samples/sec
            read = self.adc_device.read
            read()
            t0 = ticks_us()
            for i in range(n):
                self.adc_signal[i] = read()
            duration = ticks_diff(ticks_us(), t0) / 1_000_000
        elif config.cfg["mic_test_mode"]:
            # Simulate a sine wave for testing
            freq = midi_note.frequency() * (1 + 0.02 * (random.random() - 0.5))
            sample_rate = 20000
            duration = n / sample_rate
            # amp from 500 to 2000. Emulate a 12 bit ADC with
            # values oscillating around 2048, so with that amp
            # values may go from 48 to 4048 (and can go from 0 to 4095)
            amp = random.randrange(500, 2000)
            dt = 1 / sample_rate
            for i in range(n):
                self.adc_signal[i] = int(sin(6.28 * dt * i * freq) * amp + 2048)

        return duration, self.adc_signal

    @micropython.native
    def _normalize(self, signal):
        # Normalize the signal
        avg = sum(signal) // len(signal)
        for i, x in enumerate(signal):
            signal[i] = x - avg

        amplitude = (max(signal) - min(signal)) / 2

        # Scale back to a low amplitude to avoid overflow during autocorrelation
        if amplitude != 0:
            for i, x in enumerate(signal):
                # Signal now oscillates from -128 to 128
                signal[i] = int(x / amplitude * 128)
        return amplitude, signal

    @micropython.viper
    def _autocorrelation_one_pass(
        self, signal: ptr32, lag: int, size: int
    ) -> int:
        # One step of autocorrelation
        sum_signal: int = 0
        n2: int = lag
        n1: int
        for n1 in range(size - lag):
            sum_signal += signal[n1] * signal[n2]
            n2 += 1
        return sum_signal

    @micropython.native
    def _autocorrelate(self, signal):
        if not self.do_autocorrelation:
            return signal

        # Do a autocorrelation of the signal, this filters noise
        size = len(signal)
        for i in range(size):
            self.auto_signal[i] = 0
        for lag in range(size):
            self.auto_signal[lag] += self._autocorrelation_one_pass(
                signal, lag, size
            )
        return self.auto_signal

    def _sample_normalize_filter_zcr(self, midi_note):
        # Acquire signal, autocorrelate and then compute frequency
        duration, signal = self._sample_adc(midi_note)
        # >>> normalize: 66 msec
        amplitude, signal = self._normalize(signal)
        # >>> autocorrelate 553 msec if enabled
        self.auto_signal = self._autocorrelate(signal)
        # >>> zcr 95 msec
        frequency = zcr.compute_frequency(
            self.auto_signal,
            duration,
            midi_note.frequency(),
            autocorrelated=self.do_autocorrelation,
        )
        # frequency can be none
        return frequency, amplitude, duration

    async def get_note_pitch(self, midi_note):
        freqlist = []
        amplist = []
        solenoid.note_on(midi_note)
        # Wait for sound to stabilize before calling tuner
        await asyncio.sleep_ms(200)
        try:
            for iteration in range(_TUNING_ITERATIONS):
                (
                    frequency,
                    amplitude,
                    duration,
                ) = self._sample_normalize_filter_zcr(midi_note)
                nominal = midi_note.frequency()
                if frequency and nominal*0.97 < frequency < nominal*1.03:
                    freqlist.append(frequency)
                    amplist.append(amplitude)
                    # Show tuning
                    cents = midi_note.cents(frequency)
                    _logger.debug(
                        f"get_note_pitch iteration {iteration=} {midi_note=} {nominal=:.1f}Hz measured={frequency:.1f}Hz {cents=:.1f} {amplitude=}"
                    )
                else:
                    _logger.debug(
                        f"get_note_pitch iteration {iteration}  {midi_note=} no frequency could be measured, {frequency/nominal=:.2f} {amplitude=}"
                    )
                await asyncio.sleep_ms(10)  # yield, previous code was CPU bound
            # Store a sample in flash
            self._store_signal(midi_note)
        except Exception as e:
            _logger.exc(e, "Exception in get_note_pitch")
        finally:
            solenoid.note_off(midi_note)

        if len(freqlist) == 0:
            return None, 0, freqlist, amplist

        frequency = sum(freqlist) / len(freqlist)
        amplitude = sum(amplist) / len(amplist)
        return frequency, amplitude, freqlist, amplist

    def _store_signal(self, midi_note):
        frequency, amplitude, duration = self._sample_normalize_filter_zcr(
            midi_note
        )

        filename = "signal" + str(midi_note) + ".tsv"
        filename = filename.replace("-", "_")
        with open(filename, "w") as file:
            file.write(f"\t\tduration\t{duration}")
            for x in self.auto_signal:
                file.write(f"\t{x:.0f}\n")
        _logger.info(f"{filename} written")


class OrganTuner:
    def __init__(self, signal):
        self.signal = signal
        self._get_stored_tuning()
        self.tuner_queue = []
        self.start_tuner_event = asyncio.Event()
        self.organtuner_task = asyncio.create_task(self._organtuner_process())
        _logger.debug("init ok")

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
            _logger.debug(f"repeat note {note_duration=:.1f} {silence=:.1f}")
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
        global organtuner
        try:
            os.remove(config.ORGANTUNER_JSON)
        except OSError:
            pass
        for filename in os.listdir("/"):
            if filename.startswith("signal") and filename.endswith(".tsv"):
                os.remove("/" + filename)
        _logger.info("Stored tuning removed")
        # Reinitialize myself
        organtuner = OrganTuner(Signal())
    
    
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
                _logger.exc(e, "exception in _organtuner_process")
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

        except OSError:  # >>>> and json parse error
            # Make new organtuner_json file
            self.stored_tuning = {}
            for midi_note in pinout.midinotes.get_all_valid_midis():
                d = {}
                d["name"] = str(midi_note)
                d["centslist"] = []
                d["amplist"] = []
                d["pinname"] = solenoid.get_pin_name(midi_note)
                self.stored_tuning[hash(midi_note)] = d
            fileops.write_json(
                self.stored_tuning, config.ORGANTUNER_JSON, keep_backup=False
            )

            _logger.info(f"new {config.ORGANTUNER_JSON} written")
        return

    async def _update_tuning(self, midi_note):
        # Tune a single note and update organtuner.json
        _logger.info(f"_update_tuning {midi_note}")

        freq, amp, freqlist, amplist = await self.signal.get_note_pitch(
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

        _logger.info(f"_update_tuning {midi_note} stored in flash")

    def calcdb(self, amp, maxamp):
        if amp is not None and maxamp:
            dbval = 20 * log10(amp / maxamp)
            if dbval >= config.cfg["mic_signal_low"]:
                return dbval


organtuner = OrganTuner(Signal())
