import sys
from math import sin, pi, atan2
import time
import array
import math

if sys.implementation.name != "micropython":
    const = lambda x: x
    class micropython:
        def native(f):
            return f
    
class HowLong:
    def __init__( self, title ):
        self.title = title
    def __enter__( self ):
        self.t0 = time.ticks_ms()
        return self
    def __exit__( self, exc_type, exc_val, exc_traceback ):
        dt = time.ticks_diff( time.ticks_ms(), self.t0 )
        print(f"HowLong {self.title} {dt} ms" )

BUFFER_SIZE = const(1024)
# No complex arrays in Python... :-( must use lists...
exptable = [ math.e**(-1j*math.pi*i/BUFFER_SIZE) for i in range(BUFFER_SIZE) ]
#hann_table = array.array("f",  (sin(math.pi*i/BUFFER_SIZE)**2 for i in range(BUFFER_SIZE)))
# Surprisingly, the list is a bit faster than the array...
hann_table = [sin(math.pi*i/BUFFER_SIZE)**2 for i in range(BUFFER_SIZE)]
#void _fft(cplx buf[], cplx out[], int n, int step)
# about 2 or 3 ms can be shaved off if n is not passed as parameter
# and by using BUFFER_SIZE constant instead.


@micropython.native
def _fft( buf, bufoffset, out, outoffset, n, step):
    et = exptable
#	if (step < n) {
#		_fft(out, buf, n, step * 2);
#		_fft(out + step, buf + step, n, step * 2);
    if step < n:
        step2 = step*2
        _fft(out, outoffset, buf, bufoffset, n, step2)
        _fft(out, outoffset+step, buf, bufoffset+step, n, step2)
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

@micropython.native
def fft(signal, hann_windowing=False):
    if len(signal)!=BUFFER_SIZE:
        raise ValueError
    if hann_windowing:
        ht = hann_table
        signal = [ signal[i]*ht[i] for i in range(BUFFER_SIZE) ]
    out = list(signal)
    _fft( signal, 0, out, 0, len(signal), 1 )
    return signal


# return magnitude of fft between two positions
@micropython.native
def fft_abs( data, from_position, to_position ):
    return [ abs(data[i]) for i in range(from_position, to_position) ]

