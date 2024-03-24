# (c) 2023 Hermann Paul von Borries
# MIT License
# Handles response to notelist.html and note.html pages (tuning support)

import sys
import time

_implementation = sys.implementation.name
if _implementation == "micropython":
    from time import ticks_ms, ticks_diff, ticks_us
    import gc
    from machine import Pin, ADC
    if __name__ == "__main__":
        sys.path.append("/software/mpy/")
else:
    const = lambda x: x
    time.ticks_us = lambda : time.time_ns()/1_000
    time.ticks_diff = lambda x, y:x-y
    time.ticks_ms = lambda: time.time_ns()/1_000_000
    class gc:
        def collect():
            pass


from math import sin, pi

import random
import array

import fft_arrays as fft_module
import frequency
import midi
from config import config
from pinout import gpio

class Microphone:
    def __init__(self, gpio_microphone_pin, mic_test_mode):
        # Allocate memory as a first step to ensure availability
        gc.collect()
        self.buffer_size = fft_module.BUFFER_SIZE
        self.adc_signal = array.array("i", (0 for _ in range(self.buffer_size)))
        # Allocate memory for zero crossing/signal processing module
        
        if gpio_microphone_pin and not mic_test_mode:
            self.adc_device = ADC(
                Pin(gpio_microphone_pin, Pin.IN), atten=ADC.ATTN_11DB
            )
        else:
            self.adc_device = None
        
    def _sample_adc(self, midi_note):
        if self.adc_device:
            return self._sample_microphone(midi_note)
        signal =  self._generate_signal(midi_note)
        return signal
    
    def _sample_microphone(self,midi_note):
        # Get the time between samples
        step = frequency.compute_time_step_usec( midi_note.frequency()  )
        # Calculate delay needed in loop below. The magic number
        # is to compensate approximately the overhead of the loop.
        # This keeps the timing within +-2.5% of the expected time.
        delay = round(step-9)
        n = len(self.adc_signal)
        # Sample the mic. Should read about 30.000 samples/sec
        read = self.adc_device.read
        read()
        t0 = time.ticks_us()
        for i in range(n):
            time_end = time.ticks_add( ticks_us(), delay )
            self.adc_signal[i] = read()
            while time.ticks_diff(time_end,time.ticks_us())>0:
                pass
        duration = ticks_diff(ticks_us(), t0) / 1_000_000
        return duration, self.adc_signal
    
    def _generate_signal(self, midi_note):
        n = len(self.adc_signal)
        
        # Simulate a signal wave for testing
        nominal_freq = midi_note.frequency()
        r = random.random()
        # Show some frequencies in red or out of range
        freq = nominal_freq
        if True:#>>>__name__ != "__main__":
            if r<0.05:
                freq = nominal_freq*1.18
            elif r>0.95:
                freq = nominal_freq/1.18
            elif r<0.2:
                freq = nominal_freq*1.03
            elif r>0.8:
                freq = nominal_freq/1.03
        # Introduce some random in samples per period
        # to compensate possible aliasing effects
        spp = frequency.SAMPLES_PER_PERIOD + random.uniform(-0.05,0.05)
        step = 1/freq/spp
        duration = n * step
        # Check that step doesn't hit maximum sampling rate
        assert step > 1/30_000
        freq_step = 1/duration
        print(f">>> generate signal {step=:.4f}sec {freq_step=:.1f}Hz rate={1/step:.0f}samples/sec {duration=:.2f}sec samples={n} periods={duration*freq:.1f} nominal frequency={nominal_freq:.1f}Hz real frequency={freq:.1f}Hz")
        # Amplitude from 500 to 2000. Emulate a 12 bit ADC with
        # values oscillating around 2048, so with that amplitude
        # values may go from 48 to 4048 (and can go from 0 to 4095)
        amp = random.randrange(500, 2000)
        w = pi*2*step*freq
        phase = random.random()*pi*2
    
        for i in range(n): 
            # All with the same phase
            self.adc_signal[i] = (
                round(
                    sin(w*1*i+phase)*amp*0.30 +
                    sin(w*2*i+phase)*amp*0.06 +
                    sin(w*3*i+phase)*amp*0.40 +
                    sin(w*4*i+phase)*amp*0.03 +
                    sin(w*5*i+phase)*amp*0.05 
                + (random.random()*500-250)
                )
                + 2048
            )
            #self.adc_signal[i]=int(sin(_TWO_PI*step*1*i*freq+angle)*amp*0.40+2048) 
        return duration, self.adc_signal

    def frequency( self, midi_note, save_result ):
        duration, signal = self._sample_adc( midi_note )
        # for now, no amplitude.
        freq, amplitude = frequency.frequency( signal, duration, midi_note.frequency(), fft_module, midi_note, save_result )

        return freq, amplitude, duration

microphone = Microphone( gpio.microphone_pin, config.cfg["mic_test_mode"] )

if __name__ == "__main__":
    print(f"BUFFER_SIZE={microphone.buffer_size} SAMPLES_PER_PERIOD={frequency.SAMPLES_PER_PERIOD:.2f} {frequency.PLUS_MINUS_SEMITONES=} {frequency.ACCEPTED_FREQUENCY_RANGE=:.3f}")
    import os
    import scheduler
    os.umount("/")
    readsize = 1024
    progsize = 128
    lookahead = 512
    os.mount( os.VfsLfs2( bdev,readsize=readsize,progsize=progsize,lookahead=lookahead ),"/") # noqa
    print(f"VfsLfs2 mounted with {readsize=}, {progsize=}, {lookahead=}")

    # Test timing of ADC read.
    notelist = [46,48,51,53,55,56,58,60]
    notelist.extend([_ for _ in range(61,88)])
    #notelist = [46]
# test _sample_adc signal time
    sumdiff = 0
    microphone = Microphone(9,False)
    sampling_time = 0

    for note_number in notelist:
        note = midi.Note(0,note_number)
        freq = note.frequency()
        step = round(1/freq/frequency.SAMPLES_PER_PERIOD*1_000_000)
        expected = step*microphone.buffer_size/1_000_000
        note_name = str(note)
        if False:
            duration, _ = microphone._sample_adc(note)
            sumdiff += (duration-expected)
            assert abs(expected-duration)<0.01
            print(f"{note_name} {duration=:.4f} planned duration={expected:.4f} diff={(duration-expected)/expected*100:.1f}% {sumdiff=}")
        else:
            duration = step/1_000_000 * microphone.buffer_size
            print(f"{note_name} {duration=:.4f}")
        sampling_time += duration*1000
    print(f"Total time to acquire one set samples {sampling_time} msec (no processing)")

    # Test with generated signals
    microphone = Microphone(None,True)

    # Measure processing time
    midi_note = midi.Note(0,100)
    duration, signal = microphone._sample_adc( midi_note )
    with scheduler.MeasureTime("Signal processing, FFT, get_peak") as m1:
        freq, amplitude = frequency.frequency( signal, duration, midi_note.frequency(), fft_module, midi_note, False )
    processing_time = m1.time_msec*len(notelist)
    with scheduler.MeasureTime("Signal processing, FFT, get_peak, store") as m2:
        freq, amplitude = frequency.frequency( signal, duration, midi_note.frequency(), fft_module, midi_note, True )
    signal_store_time = m2.time_msec*len(notelist)
    print(f"Processing time, one note={m1.time_msec}msec all notes={processing_time}msec.  One note with store={m2.time_msec}msec all notes={signal_store_time}msec. Sampling time all notes={sampling_time}msec\n\n")

    
    # No GPIO pin, generated microphone signal
    sum_error = 0
    max_error = 0
    sum_error2 = 0
    max_error2 = 0
    not_detected = 0
    for note_number in notelist:
        note = midi.Note(0,note_number)
        note_name = str(note)
        generated_freq = note.frequency()
        freq, amplitude, duration = microphone.frequency(note, False)
        if freq:
            error = note.cents(freq)
            print(f"{note} measured freq={freq:.1f} nominal freq={note.frequency():.1f} error={error:.1f} cents")
            if error is None:
                error = 100
                
            sum_error += error
            max_error = max(abs(error),max_error)
        else:
            m = ""
            print("No frequency detected")
            not_detected+=1
        print("")
    print(f"BUFFER_SIZE={microphone.buffer_size} SAMPLES_PER_PERIOD={frequency.SAMPLES_PER_PERIOD:.2f} {frequency.PLUS_MINUS_SEMITONES=} {frequency.ACCEPTED_FREQUENCY_RANGE=:.3f}")
    storing_only = signal_store_time-processing_time
    
    print(f"Average error  {sum_error/len(notelist):4.2f} cents, max error  {max_error:4.2f} cents, Frequency {not_detected=} times, {processing_time=} msec, total one pass={sampling_time+processing_time:.0f} msec, one pass storing only={storing_only:.0f} msec")

# With BUFFER_SIZE=512 max error about 2 cents

# BUFFER_SIZE=1024 SAMPLES_PER_PERIOD=7.14 PLUS_MINUS_SEMITONES=3
# Average error  0.10 cents, max error  0.85 cents. Frequency not_detected=0 processing_time=5915 msec total one pass=19863 msec one pass storing only=22820
# (Max error varies between 0.9 and 1.2 cents)
# 3 passes means 20*3+22=82 seconds = 1 minute 20 seconds for 35 notes.

# BUFFER_SIZE=1024 SAMPLES_PER_PERIOD=8
# Average error  -0.16 cents, max error  1.30 cents. Frequency not_detected=0 processing_time=5950 msec total one pass=18390 msec (no storing)

# BUFFER_SIZE=1024 SAMPLES_PER_PERIOD=8.4
# Average error  -0.02 cents, max error  1.37 cents. Frequency not_detected=0 processing_time=5950 msec total one pass=17798 msec one pass storing only=22015

# BUFFER_SIZE=1024 SAMPLES_PER_PERIOD=9.0
# Average error  -0.22 cents, max error  1.31 cents. Frequency not_detected=0 processing_time=5915 msec total one pass=16969 msec one pass with storing=40804

# BUFFER_SIZE=2048 SAMPLES_PER_PERIOD=15
#Average error  -0.06 cents, max error  0.88 cents. Frequency not_detected=0 processing_time=11130 msec total one pass=24401.04 msec (no storing)

# BUFFER_SIZE=2048 SAMPLES_PER_PERIOD=18
# Average error  -0.19 cents, max error  0.96 cents. Frequency not_detected=0 processing_time=11060 msec total one pass=22115 msec (no storing)

# BUFFER_SIZE=2048 SAMPLES_PER_PERIOD=24
# Exceeds viable sampling rate
