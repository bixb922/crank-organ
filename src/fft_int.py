#
from math import  cos, pi, sqrt
import array

# This viper code cannot run with CPython
    
# Size of the input signal buffer
BUFFER_SIZE = const(1024)
HALF_BUFFER_SIZE = const(512) # must be BUFFER_SIZE//2


# Have cos function precalculated 
COS_TABLE_FACTOR = const(16384)
COS_TABLE_FACTOR_HALF = const(8192) # half of COS_TABLE_FACTOR
cos_table = array.array("H", (round(cos(-pi*i/BUFFER_SIZE)*COS_TABLE_FACTOR + COS_TABLE_FACTOR) for i in range(BUFFER_SIZE)))


#void _fft(cplx buf[], cplx out[], int n, int step)
# Result is scaled up by len(buf_real)
# i.e. for n=1024, real result = fftint result/1024
@micropython.viper
def _fftint( buf_real:ptr32, buf_imag:ptr32, out_real:ptr32, out_imag:ptr32, n:int, step:int, cos_table:ptr16 ):
#   if (step < n) {
    if step < n:
        step2:int = step*2
        step4:int = step*4
#       _fft(out, buf, n, step * 2);
        _fftint(out_real, out_imag, buf_real, buf_imag, n, step2, cos_table )
#       _fft(out + step, buf + step, n, step * 2);
        out_real1:ptr32 = ptr32(uint(out_real)+step4)
        out_imag1:ptr32 = ptr32(uint(out_imag)+step4)
        buf_real1:ptr32 = ptr32(uint(buf_real)+step4)
        buf_imag1:ptr32 = ptr32(uint(buf_imag)+step4)
        _fftint(out_real1, out_imag1, buf_real1, buf_imag1, n, step2, cos_table)
        
        # Multiplier to index sin/cos table with i
        multiple:int = BUFFER_SIZE//n
#       for (int i = 0; i < n; i += 2 * step) {
        i:int = 0
    
        while i < n:
            
#           cplx t = cexp(-I * PI * i / n) * out[i + step];
            # Calculate (expo_real, expo_imag) = e**(-i*pi*i/n)
            k:int = i*multiple
            expo_real:int = int(cos_table[k]) - COS_TABLE_FACTOR
            # Could be: expo_imag:int = int(sintable[k])
            # but this uses BUFFER_SIZE*4 kbytes less RAM
            expo_imag:int = int(cos_table[(k+HALF_BUFFER_SIZE)%BUFFER_SIZE]) - COS_TABLE_FACTOR
            if k >= HALF_BUFFER_SIZE:
                expo_imag = 0-expo_imag
                
            #o_real:int = out_real[i + step]
            #o_imag:int = out_imag[i + step]
            # Multiply and scale back since cos_table
            # is scaled up. Divide each product by 2 
            # to avoid overflow, then add divisor/2 to round
            # then scale back
            t_real:int = (expo_real*out_real[i + step]//2 - expo_imag*out_imag[i + step]//2 + COS_TABLE_FACTOR_HALF)//COS_TABLE_FACTOR
            t_imag:int = (expo_imag*out_real[i + step]//2 + expo_real*out_imag[i + step]//2 + COS_TABLE_FACTOR_HALF)//COS_TABLE_FACTOR
            
                
#           buf[i / 2]     = out[i] + t;
            # since t_real/t_imag is scaled back by //2
            # here //2 has also to be applied
            # Storing out_real[i]//2 and out_imag[i]//2 is a gain
            # of about 2% in CPU, not relevant
            buf_real[i>>1] = out_real[i]//2 + t_real
            buf_imag[i>>1] = out_imag[i]//2 + t_imag
        
#           buf[(i + n)/2] = out[i] - t;
            buf_real[(i + n)>>1] = out_real[i]//2 - t_real
            buf_imag[(i + n)>>1] = out_imag[i]//2 - t_imag
#       ...for      i += 2 * step) {
            i = i + step2
#       }
#   }
#}
            
#void fft(cplx buf[], int n)
#{
#	cplx out[n];
#	for (int i = 0; i < n; i++) out[i] = buf[i];
# 
#	_fft(buf, out, n, 1);
#}


@micropython.viper
def array_zero( data:ptr32, n:int):
    i:int = 0
    while i < n:
        data[i] = 0
        i = i + 1
        
@micropython.viper
def array_copy( data_from, data_to:ptr32, n:int):
    i:int = 0
    while i < n:
        data_to[i] = int(data_from[i])
        i = i + 1
@micropython.viper
def apply_window( signal:ptr32, window:ptr32, n:int):
    i = 0
    while i < n:
        # The window is scaled up.
        # Round and scale down
        signal[i] = (int(signal[i]) * window[i] + COS_TABLE_FACTOR_HALF)//COS_TABLE_FACTOR
        i = i + 1
        
@micropython.viper
def apply_hann_windowing( signal:ptr32, n:int, cos_table:ptr16 ):
    # Use same cos_table for Hann window
    i:int = 0
    while i < n:
        #cosval:int = int(cos_table[i])-COS_TABLE_FACTOR
        sinval:int = int(cos_table[(i + HALF_BUFFER_SIZE)%BUFFER_SIZE])-COS_TABLE_FACTOR
        if i < HALF_BUFFER_SIZE:
            sinval = 0 - sinval 
        #print(f"sinval {i=:3d} {k=:2d} {sinval:6d} {cosval:6d}")
        # Multiply signal by sin**2
        # Scale back after each multiplication 
        # so that no overflow occurs.
        signal[i] = (((signal[i]*sinval+COS_TABLE_FACTOR_HALF)//COS_TABLE_FACTOR)*sinval+COS_TABLE_FACTOR_HALF)//COS_TABLE_FACTOR
        i = i + 1

    
# Allocate fft buffers
buf_imag = array.array("i", (0 for _ in range(BUFFER_SIZE)) )
buf_real = array.array("i", buf_imag )
out_real = array.array("i", buf_imag )
out_imag = array.array("i", buf_imag )

    
# data: can be list or array, integer or float
def fft(data, hann_windowing=False):
    
    n = len(data)
    if n>BUFFER_SIZE:
        raise ValueError
    print(__name__, "fft", n)
    # If data is an array.array of "i" then
    # the input array could be used as buf_real instead of allocating one.
    array_copy( data, buf_real, n )
    if hann_windowing:
        apply_hann_windowing( buf_real, n, cos_table )
        if max(buf_real)>32767 or  min(buf_real)<-32768:
            #print(f"fftint {max(buf_real)=} {min(buf_real)=}")
            print(__name__, "error: fft values out of range")
            raise ValueError
    array_copy( buf_real, out_real, n )
    array_zero( buf_imag, n )
    array_zero( out_imag, n )
    _fftint( buf_real, buf_imag, out_real, out_imag, n, 1, cos_table )
    return buf_real, buf_imag


# return magnitude of fft of a segment of the frequency spectrum
def fft_abs( data, from_position, to_position ):
    x, y = data
    return [ sqrt(x[i]**2+y[i]**2) for i in range(from_position, to_position) ]

