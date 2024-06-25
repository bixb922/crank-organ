# (c) 2023 Hermann Paul von Borries
# MIT License
from micropython import const
import os
from math import sqrt

import scheduler


SIGNAL_FOLDER = const("/signals")
RAW_FILE_PREFIX = const("raw")
FFT_FILE_PREFIX = const("fft")
# Indicate the range around the nominal frequency to be detected
# PLUS_MINUS_SEMITONES=3 means 3 semitones down and 3 semitones up from
# the nominal frequency are measured. Outside that range will give no reading.
# The smaller, the better the precision and the higher the measuring time.
PLUS_MINUS_SEMITONES = 3
# Frequencies from f/ACCEPTED_FREQUENCY_RANGE to f*ACCEPTED_FREQUENCY_RANGE
# are detected.
ACCEPTED_FREQUENCY_RANGE = 2**(PLUS_MINUS_SEMITONES/12)

# SAMPLES_PER_PERIOD:
# Smaller means less error in computation of frequency
# Since the 3rd harmonic is strong, it should always show up.
# For bass notes, the microphone also might attenuate the fundamental,
# with the result that the 3rd harmonic can be stronger than the fundamental,
# if not on the spectrum, it will produce aliasing artifacts near the 
# fundamental frequency that mess up the measurement.
# So the 3rd armonic should always be present in the spectrum.
# 3rd harmonic = 3 times the fundamental in Hz. Because of Nyquist Theorem,
# the harmonic needs at least 2 samples per period, so 3*2 = 6 as the
# smallest value for SAMPLES_PER_PERIOD if the 3rd harmonic is strong.
# i.e. SAMPLES_PER_PERIOD has to be > 6.
# If much larger, there will be a certain loss of precision, since the
# buffer size is fixed and the frequency resolution of the spectrum is
# 1/duration = 1/nominal_frequency/SAMPLES_PER_PERIOD, so if the duration
# is smaller, the frequency resolution suffers.
#.
SAMPLES_PER_PERIOD = 6*ACCEPTED_FREQUENCY_RANGE
#assert SAMPLES_PER_PERIOD >=6*ACCEPTED_FREQUENCY_RANGE

def vertex( x1, y1, x2, y2, x3, y3 ):
    # return vertex (maximum or minimum) of parabola
    # that passes through (x1,y1), (x2,y2) and (x3,y3)
    # Calculate parameters of parabola
    denom = (x1 - x2) * (x1 - x3) * (x2 - x3)
    A = (x3 * (y2 - y1) + x2 * (y1 - y3) + x1 * (y3 - y2)) / denom
    B = (x3*x3 * (y1 - y2) + x2*x2 * (y3 - y1) + x1*x1 * (y2 - y3)) / denom
    C = (x2 * x3 * (x2 - x3) * y1 + x3 * x1 * (x3 - x1) * y2 + x1 * x2 * (x1 - x2) * y3) / denom
    # Calculate the location of the maximum (or minimum)
    xv = -B / (2*A)
    yv = C - B*B / (4*A)
    return xv, yv

def find_max( signal ):
    # Finds the peak frequency in spectrum
    # Precondition: the range is limited so that there is only one peak
    # This is fast, normally takes about 1-2ms, since native functions are used
    maxsignal = max(signal)
    avgsignal = sum(signal)/len(signal)
    print(f"find_max {maxsignal=} {avgsignal=} {maxsignal/avgsignal=}")
    # If there is no signal at the mic, maxsignal is about avgsignal*3
    # If there is a good signal at the mic, maxsignal is about avgsignal*10 
    # to avgsignal*30
    if maxsignal < avgsignal*5:
        raise ValueError
    # Get position where maximum occurs
    p = signal.index(maxsignal)
    # Return (x,y) before maximum, at maximum and after maximum
    return p-1, signal[p-1], p, signal[p], p+1, signal[p+1]

def get_peak( abs_fft ):
    x1, y1, x2, y2, x3, y3  = find_max( abs_fft )
    xv, yv = vertex( x1, y1, x2, y2, x3, y3 ) 
    return xv


def frequency( signal, duration, nominal_freq, fft_module, midi_note, save_result ):
    signal_len=len(signal)
    amplitude = compute_amplitude(signal)
    time_step = duration/signal_len
    freq_step = 1/duration
    if save_result:
        with scheduler.MeasureTime("save signal to flash"):
            save( signal, duration, midi_note, time_step, RAW_FILE_PREFIX )

    # Search in a range of some semitones around the fundamental.
    # In this range there is no harmonic expected, so find_max needs to
    # find the only peak there is. (Harmonics are at least 1 octave away).
    # If the note is more semitones out of tune
    # no frequency will be found.
    # The range is also in line with the sampling rate,
    # see comment where SAMPLES_PER_SEC is defined.
    # SAMPLES_PER_SEC and ACCEPTED_FREQUENCY_RANGE must be defined
    # so thatthe from and to positions are not at the border of the fft result
    # (at lest 3 elements away from those) to avoid IndexError 
    from_position = int(nominal_freq/ACCEPTED_FREQUENCY_RANGE/freq_step)-3
    to_position = int(nominal_freq*ACCEPTED_FREQUENCY_RANGE/freq_step)+3
    
    print(f"search peak fft from {from_position}={from_position*freq_step}Hz to {to_position}={to_position*freq_step}Hz {nominal_freq=}  {amplitude=} {duration=}")
    result = fft_module.fft(signal, True)

    if save_result:
        with scheduler.MeasureTime("save fft to flash"):
            save( fft_module.fft_abs(result, 0, len(result)), duration, midi_note, freq_step, FFT_FILE_PREFIX )

    # Get abs of the fft only in the range of desired
    # frequency range
    # get abs(result) takes < 1ms
    result = fft_module.fft_abs( result, from_position, to_position )

        # Search for peak frequency and interpolate
    freq =  (get_peak( result ) + from_position) * freq_step
    return freq, amplitude

def save( signal, duration, midi_note, step, prefix ):
    # Save a signal, can be raw or FFT in /signals folder 
    filename = f"{SIGNAL_FOLDER}/{prefix}{midi_note.midi_number}.tsv"
    if prefix == FFT_FILE_PREFIX:
        units = "Hz"
    elif prefix == RAW_FILE_PREFIX:
        units = "ms"
    else:
        units = "?"
    # This takes about 350 ms, two times for each note 
    # (one call to save for raw signal, one call to save for FFT)
    with open( filename, "w" ) as file:
        # Write header row
        file.write(f"duration:\t{duration}\tlen:\t{len(signal)}\tstep {units}:\t{step}\n")
        # Write data, one integer per line.
        for v in signal:
            file.write(f"{round(v)}\n")
        print("file", filename, "written")
            
def compute_amplitude( signal ):
    avgsignal =  sum( s for s in signal )/len(signal)
    return sqrt(sum( (s-avgsignal)**2 for s in signal ))/len(signal)
            
def compute_time_step_usec( nominal_frequency  ):
    return 1/nominal_frequency/SAMPLES_PER_PERIOD*1_000_000

def clear_stored_signals():
    for filename in os.listdir(SIGNAL_FOLDER):
            try:
                os.remove(filename)
            except OSError:
                pass

