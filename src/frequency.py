import time
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
    denom = (x1 - x2) * (x1 - x3) * (x2 - x3);
    A = (x3 * (y2 - y1) + x2 * (y1 - y3) + x1 * (y3 - y2)) / denom
    B = (x3*x3 * (y1 - y2) + x2*x2 * (y3 - y1) + x1*x1 * (y2 - y3)) / denom
    C = (x2 * x3 * (x2 - x3) * y1 + x3 * x1 * (x3 - x1) * y2 + x1 * x2 * (x1 - x2) * y3) / denom

    xv = -B / (2*A)
    yv = C - B*B / (4*A)
    return xv, yv

# signal ---> abs_fft
def find_max( signal ):
    # Takes about 1-2ms
    maxsignal = max(signal)
    avgsignal = sum(signal)/len(signal)
    print(f"find_max {maxsignal=} {avgsignal=} {maxsignal/avgsignal=}")
    # If signal/noise is low, don't seek for the frequency
    if maxsignal < avgsignal*5:
        raise ValueError
    # Get position where maximum occurs
    p = signal.index(maxsignal)
    return p-1, signal[p-1], p, signal[p], p+1, signal[p+1]

def get_peak( abs_fft ):
    x1, y1, x2, y2, x3, y3  = find_max( abs_fft )
    xv, yv = vertex( x1, y1, x2, y2, x3, y3 ) 
    return xv


def frequency( signal, duration, nominal_freq, fft_module, midi_note ):
    signal_len=len(signal)
    amplitude = compute_amplitude(signal)
    time_step = duration/signal_len
    freq_step = 1/time_step/signal_len
    save( signal, duration, midi_note, time_step, "signal")
    
    # 1.4 is a factor of about 6 semitones up and 6 semitones down.
    # In this range there is no harmonic expected.
    # This spans half an octave up and half down to search
    # for peak frequency.
    # But on the other hand if the note is 6 semitones out of tune
    # please tune first with hand tuner...
    from_position = round(nominal_freq/1.4/freq_step)
    to_position = round(nominal_freq*1.4/freq_step)
    print(f"search peak fft from {from_position}={from_position*freq_step}Hz to {to_position}={to_position*freq_step}Hz {nominal_freq=}  {amplitude=} {duration=}")
    with HowLong("fft"):
        result = fft_module.fft(signal, True)
    # >>>> save last result
    save( fft_module.fft_abs(result, 0, len(result)), duration, midi_note, freq_step, "fft")
    
    #Get abs of the fft only in the range of desired
    # frequency +- 1 semitone
    # get abs(result) takes < 1ms
    result = fft_module.fft_abs( result, from_position, to_position )

    # Search for peak frequency and interpolate
    return (get_peak( result ) + from_position) * freq_step, amplitude

def save( signal, duration, midi_note, step, prefix ):
    filename = f"{prefix}{midi_note.midi_number}.tsv"
    if prefix == "fft":
        units = "Hz"
    else:
        units = "ms"
    with open( filename, "w" ) as file:
        file.write(f"duration:\t{duration}\tlen:\t{len(signal)}\tstep {units}:\t{step}\n")
        for v in signal:
            file.write(f"{round(v)}\n")
        print("file", filename, "written")
            
def compute_amplitude( signal ):
    avgsignal =  sum( s for s in signal )/len(signal)
    return sum( abs(s-avgsignal) for s in signal )/len(signal)
            
def compute_time_step_usec( nominal_frequency, samples_per_period=8 ):
    # set samples_per_period = 8 here
    # Less than 8 samples per period tends to give more
    # undesirable aliasing effects
    return 1/nominal_frequency/samples_per_period*1_000_000
