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
                t = position - 1 + interpolate1(
                signal[position-1],
                signal[position] )
                if last_t is not None:
                    yield (t - last_t)*time_units 
                last_t = t
        prev_sample = sample
    return

# def compute_frequency( signal, duration ) :

    #Find first and last negative to positive zero crossing
    # first_crossing = None
    # last_crossing = None
    
    #First step of iteration does never detect zero crossing
    # prev_sample = signal[0]
    
    # crossing_count = 0
    
    # for position, sample in enumerate(signal):
        # if prev_sample < 0 and sample >= 0:
            #Negative to positive zero crossing detected
            # crossing_count += 1
            # if first_crossing is None:
                #First zero crossing detected
                # first_crossing = position 
            # else:
                #Update position of the last zero crossing
                # last_crossing = position 
        # prev_sample = sample
        
    # if crossing_count < 2:
        #Must find at least 2 crossings = 1 cycle, can't compute frequency
        # raise ValueError

    # Interpolate, the zero crossing is somewhere between position-1 and position    

    # order = 2
    # Best results with order 2
    # if order == 1:
        # first_crossing = first_crossing - 1 + \
            # interpolate1( signal[first_crossing-1], \
                        # signal[first_crossing] )
        # last_crossing = last_crossing - 1  + \
            # interpolate1( \
                        # signal[last_crossing-1], \
                        # signal[last_crossing] )
    # elif order == 2:
        # first_crossing = first_crossing - 2 + interpolate2(
            # signal[first_crossing-2],
            # signal[first_crossing-1],
            # signal[first_crossing] )
        # last_crossing = last_crossing - 2  + interpolate2(
            # signal[last_crossing-2],
            # signal[last_crossing-1],
            # signal[last_crossing] )
    # elif order == 3:
        # first_crossing = first_crossing - 2 + interpolate3(
            # signal[first_crossing-3],
            # signal[first_crossing-2],
            # signal[first_crossing-1],
            # signal[first_crossing] )
        # last_crossing = last_crossing - 2  + interpolate3(
            # signal[last_crossing-3],
            # signal[last_crossing-2],
            # signal[last_crossing-1],
            # signal[last_crossing] )
    #Else: no interpolation (order 0)


    # duration_of_begin_to_end = (last_crossing - first_crossing) / len(signal) * duration

    # if duration_of_begin_to_end == 0:
        # with crossing_count>2 a complete cycle should have been found
        # raise ValueError

    # return (crossing_count - 1)/duration_of_begin_to_end

def zcr_list( signal, duration ):
    return [ x for  x  in gen_zeros( signal, duration ) ]


def compute_frequency( signal, duration ):
    # Get list of zeros, test if error is large
    zeros = zcr_list( signal, duration )
    n = len(zeros)
    if n == 0:
        raise ValueError
    sumx = 0
    for x in zeros:
        sumx += x
    avg = sumx/n
    diff = 0
    for x in zeros:
        diff += (x - avg)**2
    stddev = sqrt( diff/n )
    if stddev/avg > 0.03:
        raise ValueError

    if len(zeros) <= 4:
        return sum(zeros)/len(zeros)
    else:
        n = (len(zeros)*2)//3
        return 1/sum( zeros[0:n] ) * n
        

def interpolate1( y1, y2 ):
    # Order 1 interpolation
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
    print(f"interpolacion2 mala {r1=} {r2=}")
    exit()

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
