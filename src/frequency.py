import time
import os

# Must be clearly > 2, these is the number of samples per period
# of the nominal frequency. 
# Smaller means less error in computation of frequency
# But 5 or smaller means that higher armonics may distort the FFT
# because they may show up as noise...
# So the 3rd armonic should at least always show up.
# 3rd armonic = 2.5 times the fundamental. Because of Nyquist
# the fundamental needs > 2 samples per period, so 2.5*2 = 5 as the
# smallest value for SAMPLES_PER_PERIOD if the 3rd harmonic is strong.
SAMPLES_PER_PERIOD = 6

class HowLong:
    def __init__( self, title ):
        self.title = title
    def __enter__( self ):
        self.t0 = time.ticks_ms()
        return self
    def __exit__( self, exc_type, exc_val, exc_traceback ):
        dt = time.ticks_diff( time.ticks_ms(), self.t0 )
        print(f"HowLong {self.title} {dt} ms" )
    
def vertex( x1, y1, x2, y2, x3, y3 ):
    denom = (x1 - x2) * (x1 - x3) * (x2 - x3)
    A = (x3 * (y2 - y1) + x2 * (y1 - y3) + x1 * (y3 - y2)) / denom
    B = (x3*x3 * (y1 - y2) + x2*x2 * (y3 - y1) + x1*x1 * (y2 - y3)) / denom
    C = (x2 * x3 * (x2 - x3) * y1 + x3 * x1 * (x3 - x1) * y2 + x1 * x2 * (x1 - x2) * y3) / denom

    xv = -B / (2*A)
    yv = C - B*B / (4*A)
    return xv, yv

# signal ---> abs_fft
def find_max( signal ):
    # Finds the peak frequency in spectrum
    # Precondition: the range is limited so that there is only one peak
    # This normally takes about 1-2ms
    maxsignal = max(signal)
    avgsignal = sum(signal)/len(signal)
    print(f"find_max {maxsignal=} {avgsignal=} {maxsignal/avgsignal=}")
    # If signal/noise is low, don't seek for the frequency
    # If there is no signal at the mic, maxsignal is about avgsignal*3
    # If there is a good signal at the mic, maxsignal is about avgsignal*10 or more
    if maxsignal < avgsignal*5:
        raise ValueError
    # Get position where maximum occurs
    p = signal.index(maxsignal)
    return p-1, signal[p-1], p, signal[p], p+1, signal[p+1]

def get_peak( abs_fft ):
    x1, y1, x2, y2, x3, y3  = find_max( abs_fft )
    xv, yv = vertex( x1, y1, x2, y2, x3, y3 ) 
    return xv


def frequency( signal, duration, nominal_freq, fft_module, midi_note, save_result ):
    with HowLong("Process signal, FFT and get frequency"):
        signal_len=len(signal)
        amplitude = compute_amplitude(signal)
        time_step = duration/signal_len
        freq_step = 1/duration
        if save_result:
            save( signal, duration, midi_note, time_step, "signal")

        # 1.4 is a factor of about 6 semitones up and 6 semitones down.
        # In this range there is no harmonic expected, so find_max needs to
        # find the only peak there is.
        # This spans half an octave up and half an octave down to search
        # for the peak frequency.
        # If the note is 6 semitones out of tune
        # there is something seriously wrong..... so it doesn't make
        # much sense to search in a larger range.
        from_position = round(nominal_freq/1.4/freq_step)
        to_position = round(nominal_freq*1.4/freq_step)
        print(f"search peak fft from {from_position}={from_position*freq_step}Hz to {to_position}={to_position*freq_step}Hz {nominal_freq=}  {amplitude=} {duration=}")
        result = fft_module.fft(signal, True)

        if save_result:
            save( fft_module.fft_abs(result, 0, len(result)), duration, midi_note, freq_step, "fft")

        # Get abs of the fft only in the range of desired
        # frequency range
        # get abs(result) takes < 1ms
        result = fft_module.fft_abs( result, from_position, to_position )

    # Search for peak frequency and interpolate
    return (get_peak( result ) + from_position) * freq_step, amplitude

def save( signal, duration, midi_note, step, prefix ):
    # Save a signal, be it raw or FFT
    filename = f"{prefix}{midi_note.midi_number}.tsv"
    if prefix == "fft":
        units = "Hz"
    else:
        units = "ms"
    # This takes about 350 ms, two times for each note 
    # (one call to save for raw signal, one call to save for FFT)
    with open( filename, "w" ) as file:
        file.write(f"duration:\t{duration}\tlen:\t{len(signal)}\tstep {units}:\t{step}\n")
        for v in signal:
            file.write(f"{round(v)}\n")
        print("file", filename, "written")
            
def compute_amplitude( signal ):
    avgsignal =  sum( s for s in signal )/len(signal)
    return sum( abs(s-avgsignal) for s in signal )/len(signal)
            
def compute_time_step_usec( nominal_frequency  ):
    return 1/nominal_frequency/SAMPLES_PER_PERIOD*1_000_000

def clear_stored_signals():
    for filename in os.listdir(""):
        if filename.endswith(".tsv") and (filename.startswith("fft") or
                                         filename.startswith("signal")):
            os.remove(filename)
        