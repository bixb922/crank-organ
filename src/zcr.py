# (c) 2023 Hermann Paul von Borries
# MIT License
# zero crossing frequency measurement

# Only one generator to yield list of zero crossings
# compute_frequency gets first and last
# zcr_list generates list
from math import sqrt

def gen_zeros( signal, duration ):
    # First step of iteration does never detect zero crossing
    prev_sample = signal[0]
    last_t = None
    time_units = duration / len(signal)
    for position, sample in enumerate(signal):
        if prev_sample < 0 and sample >= 0:
            # Negative to positive zero crossing detected
            if position >= 1:
                # Use linear interpolation to get approximation to real crossing
                # Linear or second order seem best.
                t = position - 1 + interpolate1(
                    signal[position-1],
                    signal[position]
                    )
                if not( position-1 <= t <= position ):
                    assert False
                
                if last_t is not None:
                    yield (t - last_t)*time_units 
                last_t = t
        prev_sample = sample
    return



def zcr_list( signal, duration ):
    return [ x for  x  in gen_zeros( signal, duration ) ]

def average( signal ):
    return sum( signal ) / len( signal )

def compute_frequency( signal, duration, estimated_freq ):

    # Get list of zeros, test if error is large
    zeros = zcr_list( signal, duration )
    n = len(zeros)
    if n == 0:
        return None
    
    # Validate the information received
    # Get average and standard deviation
    if False:
        avg = average( zeros )
        diff = 0
        for x in zeros:
            diff += (x - avg)**2
        stddev = sqrt( diff/n )
        # If deviation is too big, bad measurement
        if stddev/avg > 0.03:
            return None

    if len(zeros) <= 4:
        # If few, average all
        freq =  1/average( zeros )
    else:
        # If many zeros, take only first part, since the first part
        # of the autocorrelated signal is the best.
        n = (len(zeros)*2)//3
        freq =  1/average( zeros[0:n] )
	# See if a harmonic fits
	for h in [1,1.5,2,2.5]:
		if estimated_freq/1.25 < freq/h < estimated_freq*1.25:
			print(f">>>harmonic {h=} detected {freq=} {estimated_freq=} {freq/estimated_freq=}")
			return freq/h
	print(f">>>NO harmonic detected {freq=} {estimated_freq=} {freq/estimated_freq=}")
    return freq    
        

def interpolate1( y1, y2 ):
    # Order 1 interpolation/linear interpolation
    return  -y1/( y2 - y1 )

import math

def interpolate2( y1, y2, y3 ):
    # Order 2 is best behaviour, better than 1 or 3odd
    a = ((y1-y3)+2*(y2-y1))/(-2)
    if a == 0:
        return interpolate1( y2, y3 )
    b = (y2-y1) - a
    c = y1
    sq = math.sqrt( b*b - 4*a*c )
    r1 = (-b + sq)/2/a
    r2 = (-b - sq)/2/a
    if 0<=r1<=2:
        return r1
    if 0<=r2<=2:
        return r2
    assert False, "zcr.interpolate2 error"
    

def interpolate3( y1, y2, y3, y4 ):
    # Odd cubic function
     # y = a*x**3 + bx**2 +cx + d
##    d = y1
##    a + b + c + d = y2, 
##    8a + 4b + 2c + d = y3, 
##    27a + 9b + 3c + d = y4
     
## Reescrito para Wolfram Alpha
##     x4=e, x1 + x2 + x3 + x4 = f, 9x1 + 4x2 + 2x3 + x4 = g, 27x1 + 8x2 + 3x3 + x4 = h

    
    a = (-y1 + 3*y2 - 3*y3 + y4 ) /6
    b = y1 - 5*y2/2 + 2*y3 - y4/2
    c = (-11*y1 + 18*y2 - 9*y3 + 2*y4)/6
    d = y1 

##    print("")    
##    print(y1, y2, y3, y4 )
##    print([a*x**3 + b*x**2 + c*x + d for x in range(4)])
    x=2.5
    for i in range(5):
        x = x - (a*x**3 + b*x**2 + c*x + d)/(3*a*x**2 + 2*b*x + c)
##        print(f"{x=:.4f}   {a*x**3 + b*x**2 +c*x + d=:.4f}")
    return x


##from random import random
##def rr(a,b):
##    return random()*(b-a)+a
##
##for x,y,z,t  in [(rr(-1,-0.2),rr(-1,0.1),rr(-1,0.05), rr(0.001,1)) for i in range(3)]:
##    a = interpolate3(x,y,z,t)
##    if a < 3 or a > 4:
##        print(f"fuera rango {x=} {y=} {z=} {t=} {a=}")
##

#Traceback (most recent call last):
#File "crank-organ/src/tinyweb/server.py", line 569, in _handler
#File "crank-organ/src/webserver.py", line 319, in change_mode
#File "crank-organ/src/webserver.py", line 54, in set_mode
#File "crank-organ/src/organtuner.py", line 357, in
#File "crank-organ/src/organtuner.py", line 54, in _init
#File "crank-organ/src/organtuner.py", line 71, in _test_performance
#File "crank-organ/src/organtuner.py", line 164, in _sample_normalize_filter_zcr
#File "crank-organ/src/zcr.py", line 117, in compute_frequency
#ValueError: