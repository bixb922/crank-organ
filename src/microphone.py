# (c) 2023 Hermann Paul von Borries
# MIT License
# Handles response to notelist.html and note.html pages (tuning support)

import sys
import time
import fft_arrays as fft_module

_implementation = sys.implementation.name
if _implementation == "micropython":
    import os
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

import frequency

import midi

from config import config
from pinout import gpio

# Sample rate is about max 35kHz for a ESP32-S3 at 240Mhz
# so 1024 samples gathers about 12 msec of data at maximum rate.
# To get enough periods of the signal, the sampling has
# to be slowed down. This allows to process more periods, resulting
# in more precision. 
_BUFFER_SIZE = const(1024)



class Microphone:
    def __init__(self, gpio_microphone_pin, mic_test_mode):
        # Allocate memory as a first step to ensure availability
        gc.collect()
        #>>>TRY WITH "f" instead of "i"
        self.adc_signal = array.array("i", (0 for _ in range(_BUFFER_SIZE)))
        # Allocate memory for zero crossing/signal processing module
        
        if gpio_microphone_pin and not mic_test_mode:
            self.adc_device = ADC(
                Pin(gpio_microphone_pin, Pin.IN), atten=ADC.ATTN_11DB
            )
            print(">>>> ADC CONFIGURED, gen signal", mic_test_mode)
        else:
            self.adc_device = None
            print(">>>NO MICROPHONE CONFIGURED; GENERATE SIGNAL", mic_test_mode)
        
    def _sample_adc(self, midi_note):
        if self.adc_device:
            return self._sample_microphone(midi_note)
        return self._generate_signal(midi_note)
    
    def _sample_microphone(self,midi_note):
        print(">>> sample microphone")
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
        sumdiff = 0
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
        freq = midi_note.frequency()
        r = random.random()
        # Show some frequencies in red or out of range
        if r<0.2:
            freq = freq*1.03
        elif r>0.8:
            freq = freq/1.03
        if r < 0.05:
            freq = freq*1.5
        elif r >0.95:
            freq = freq/1.5
        # Introduce some random in samples per period
        # to mimic real frequency variations
        spp = 8 + (random.random()-0.3)
        step = 1/freq/spp
        duration = n * step
        # Check that step doesn't hit maximum sampling rate
        assert step > 1/30_000
        print(f">>> generate signal {step=:.6f} rate={1/step:.0f} {duration=:.2f} samples={n} periods={duration*freq:.1f} nominal frequency={freq}")
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

    def frequency( self, midi_note ):
        duration, signal = self._sample_adc( midi_note )
        # for now, no amplitude.
        freq, amplitude = frequency.frequency( signal, duration, midi_note.frequency(), fft_module, midi_note )

        return freq, amplitude, duration


microphone = Microphone( gpio.microphone_pin, config.cfg["mic_test_mode"] )

if __name__ == "__main__":
    # Test timing of ADC read.
    notelist = [46,48,51,53,55,56,58,60]
    notelist.extend([_ for _ in range(61,88)])
    #notelist = [46]
    # test _sample_adc signal time
    # >>>> DISABLED
    if False:
        sumdiff = 0
        microphone = Microphone(9,False)
        total0 = time.ticks_ms()

        for note_number in notelist:
            note = midi.Note(0,note_number)
            note_name = str(note)
            duration, _ = microphone._sample_adc(note)
            freq = note.frequency()
            step = round(1/freq/8*1_000_000)
            expected = step*_BUFFER_SIZE/1_000_000
            sumdiff += (duration-expected)
            print(f"{note_name} {duration=:.4f} planned duration={expected:.4f} diff={(duration-expected)/expected*100:.1f}% {sumdiff=}")
        total1 = time.ticks_ms()
        print(f"Total time to acquire samples {time.ticks_diff(total1,total0)} (no processing)")


    # No GPIO pin, generated microphone signal
    # Test with generated signals
    microphone = Microphone(None,True)
    sum_error = 0
    max_error = 0
    sum_error2 = 0
    max_error2 = 0
    not_detected = 0
    for note_number in notelist:
        note = midi.Note(0,note_number)
        note_name = str(note)
        generated_freq = note.frequency()
        t0 = time.ticks_ms()
        freq, amplitude, duration = microphone.frequency(note)
        #>>>> pending: store last
        dt = time.ticks_diff(time.ticks_ms(),t0)
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
    print(f"Average error  {sum_error/len(notelist):4.2f} cents, max error  {max_error:4.2f} cents. Frequency {not_detected=}")

# Best output
#    *Bb2(46)
#    duration=0.5493 expected=0.5489 diff=0.1% sumdiff=0.000443995
#    ....
#    *Eb6(87)
#    duration=0.0524 expected=0.0512 diff=2.4% sumdiff=0.0237669
# Diferencias son < 3.5%.
# sumdiff es la suma (sin abs) de todas las diferencias como cifra de mérito (segundos)

# Performance (jan 2024)
#    HowLong generate signal 123 ms
#    HowLong normalize 34 ms
#    HowLong lowpass 20 ms
#    HowLong autocorrelate 58 ms
#    HowLong zcr.frequency 3 ms
# Example:
#    *Eb6(87)   estimated=1244.51 freq=1244.34 error=-0.24 cents zeros=18 processing 240 msec
#    Average error  -0.11 cents, max error  0.29
