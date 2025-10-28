# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# Handles response to notelist.html and note.html pages (tuning support)

import time
from time import ticks_diff, ticks_us
import gc
from machine import Pin, ADC


from math import sin, pi

import random
from array import array

import fft_arrays as fft_module # Allow for different fft modules
import frequency

class Microphone:
    def __init__(self, gpio_microphone_pin, mic_test_mode):
        # Allocate memory as a first step to ensure availability
        gc.collect()
        self.buffer_size = fft_module.BUFFER_SIZE
        self.adc_signal = array("i", (0 for _ in range(self.buffer_size))) # type:ignore
        self.mic_test_mode = mic_test_mode
        if gpio_microphone_pin and not mic_test_mode:
            self.adc_device = ADC(
                Pin(gpio_microphone_pin, Pin.IN), atten=ADC.ATTN_11DB
            )
        else:
            self.adc_device = None
        
    def _sample_adc(self, midi_note):
        if self.adc_device:
            return self._sample_microphone(midi_note)
        if self.mic_test_mode:
            return  self._generate_signal(midi_note)
        # Return dummy signal, no frequency
        return 1, bytearray(10)
    
    def _sample_microphone(self,midi_note):
        # Get the time between samples
        step = frequency.compute_time_step_usec( midi_note.frequency()  )
        # Calculate delay needed in loop below. The magic number
        # when calculating delay
        # is to compensate approximately the overhead of the loop.
        # This keeps the timing within +-2.5% of the expected time.
        delay = round(step-9)
        # Special case: if midi_note is 127, sample as fast
        # as possible
        if midi_note.midi_number == 127:
            delay = 0
        n = len(self.adc_signal)
        # Sample the mic. Should be able to read up to 30.000 samples/sec
        read = self.adc_device.read  # type:ignore
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
        # Randomly show some frequencies in red or out of range
        freq = nominal_freq
        if True:
            if r<0.05:
                freq = nominal_freq*1.18
            elif r>0.95:
                freq = nominal_freq/1.18
            elif r<0.2:
                freq = nominal_freq*1.03
            elif r>0.8:
                freq = nominal_freq/1.03
        # Introduce some randomness in samples per period
        # to compensate possible aliasing effects
        spp = frequency.SAMPLES_PER_PERIOD + random.uniform(-0.05,0.05)
        step = 1/freq/spp
        duration = n * step
        # Check that step doesn't hit maximum sampling rate
        #assert step > 1/30_000
        if step < 1/30_000:
            print(f"Warning: step too small for sampling rate {freq=}, {frequency.SAMPLES_PER_PERIOD=} {step=} {1/30_000=}")
        freq_step = 1/duration
        print(f"generate debugging signal {step=:.4f}sec {freq_step=:.1f}Hz rate={1/step:.0f}samples/sec {duration=:.2f}sec samples={n} periods={duration*freq:.1f} nominal frequency={nominal_freq:.1f}Hz real frequency={freq:.1f}Hz")
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

        freq, amplitude = frequency.frequency( signal, duration, midi_note.frequency(), fft_module, midi_note, save_result )        
        return freq, amplitude, duration
    
    def save_hires_signal(self, midi_note):
        from drehorgel import config
        if self.adc_device and config.cfg.get("mic_store_signal", False):
            read = self.adc_device.read  # type:ignore
            # 4000 samples at 30.000 samples/sec means 0.116 sec
            # of data. At 100 Hz for the lowest signal, this means
            # at least 10 periods of the signal. 
            # At 2500 Hz for the highest signal, this means about 250 periods
            # with about 12 samples per period.
            print(">>>High resolution signal for", midi_note, "start" )
            s = array("i", (0 for _ in range(4000))) # type:ignore
            t0 = time.ticks_ms()
            for i in range(len(s)):
                s[i] = read()
            d = time.ticks_diff(time.ticks_ms(), t0)/1000
            frequency.save( s, d, midi_note, d/len(s), frequency.HIRES_FILE_PREFIX )
            print(">>>High resolution signal saved for", midi_note, "duration=", d )


# Performance test of tuner
# With BUFFER_SIZE=512, the maximum error about 2 cents

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
