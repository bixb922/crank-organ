import sys
from math import sin
import math

if sys.implementation.name != "micropython": # type:ignore
    def const(x):
        return x
    # Make micropython decorator a no-op
    class micropython:
        def native(self):
            return self
else:
    from micropython import const # type:ignore
    

# Sample rate is about max 35kHz for a ESP32-S3 at 240Mhz
# so 1024 samples can be gathered within 12 msec if sampling at maximum rate.
# To get enough samples of the signal, the sampling has
# to be slowed down. 

BUFFER_SIZE = const(1024) 

# No complex arrays, use list
exptable = [ math.e**(-1j*math.pi*i/BUFFER_SIZE) for i in range(BUFFER_SIZE) ]

# Surprisingly, the list is a bit faster than the array...
# This is the von Hann window for FFT
hann_table = [sin(math.pi*i/BUFFER_SIZE)**2 for i in range(BUFFER_SIZE)]

# about 2 or 3 ms can be shaved off if n is not passed as parameter
# and by using BUFFER_SIZE constant instead.
@micropython.native  # type:ignore
def _fft_recursive( buf, bufoffset, out, outoffset, n, step):
#void _fft(cplx buf[], cplx out[], int n, int step)
    et = exptable # Make twiddle factor table local, it's faster
#	if (step < n) {
#		_fft(out, buf, n, step * 2);
#		_fft(out + step, buf + step, n, step * 2);
    if step < n:
        step2 = step*2
        _fft_recursive(out, outoffset, buf, bufoffset, n, step2)
        _fft_recursive(out, outoffset+step, buf, bufoffset+step, n, step2)
        #multiple = BUFFER_SIZE//n # only allow n == BUFFER_SIZE
#		for (int i = 0; i < n; i += 2 * step) {
        for i in range(0,n,step2):
#			cplx t = cexp(-I * PI * i / n) * out[i + step];
            #t = et[i*multiple] * out[outoffset+i+step]
            t = et[i] * out[outoffset+i+step]
#			buf[i / 2]     = out[i] + t;
            oi = out[outoffset+i]
            buf[bufoffset+i//2] = oi + t
#			buf[(i + n)/2] = out[i] - t;
            buf[bufoffset+(i+n)//2] = oi - t
#		}
#	}
#}
                      
#void fft(cplx buf[], int n)
#{
#	cplx out[n];
#	for (int i = 0; i < n; i++) out[i] = buf[i];
# 
#	_fft(buf, out, n, 1);
#}

@micropython.native  # type:ignore
def fft(signal, hann_windowing=False):
    if len(signal)!=BUFFER_SIZE:
        raise ValueError
    if hann_windowing:
        # Apply windowing function
        ht = hann_table
        signal = [ signal[i]*ht[i] for i in range(BUFFER_SIZE) ]
    out = list(signal)
    _fft_recursive( signal, 0, out, 0, len(signal), 1 )  # type:ignore
    return signal


# return magnitude of a slice of the fft
@micropython.native  # type:ignore
def fft_abs( data, from_position, to_position ):
    return [ abs(data[i]) for i in range(from_position, to_position) ]
