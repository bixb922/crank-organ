# >>> boton reset stored tuning - borra organtuner.json
# >>> max para db se calcula, no es fijo.
# >>> esconder valores en la UI que no son medidos: -9999, null
# >>> measure "no signal" ???
import sys
import os
import array
from time import ticks_ms, ticks_diff, ticks_us
import gc
import asyncio
import json
from machine import Pin, ADC
from math import sin
import random

import zcr
import solenoid
from minilog import getLogger
import config
import modes
import pinout
import midi


## PIN NUMBER - ADD TO ORGANTUNER.JSON

_BUFFER_SIZE = const(1000)
_TUNING_ITERATIONS = const(5)  

def _init():
    global _logger
    # Allocate buffers only once
    global adc_signal, auto_signal
    # MIC ADC pin
    global adc_device
    # Queue for pending MIDI notes to be tuned, task to consume that queue and
    # event to start tuning going.
    global  tuner_queue
    global organtuner_task, start_tuner_event
  

    _logger = getLogger( __name__ )
    # Allocate memory as a first step to ensure availability
    gc.collect()   
    adc_signal = array.array("i", (0 for _ in range(_BUFFER_SIZE)))
    auto_signal = array.array("f", adc_signal) 
    
    
    if pinout.microphone_pin and not config.cfg["mic_test_mode"]:
        adc_device = ADC( Pin( pinout.microphone_pin, Pin.IN ), atten=ADC.ATTN_11DB )
    else:
        _logger.debug("No microphone, test mode= {config.cfg['mic_test_mode']}")
        adc_device = None 
  
    _test_performance()
   
    # Test if stored tuning exists on flash, create if not
    _get_stored_tuning()
    
    tuner_queue = []
    start_tuner_event = asyncio.Event()
    organtuner_task = asyncio.create_task( _organtuner_processs() )
    _logger.debug("init ok")
    
def _test_performance( ):
    # Tune one note, measure timings and calculate limits of this tuning.
    try:
        midi_note = midi.find( pinout.all_valid_midis, 69 ) # test A440
    except:
        _logger.debug("No midi note 69 found")
        return
    freq, amplitude, duration = _sample_normalize_filter_zcr( midi_note )    
    samples_per_sec = 1/duration*len(adc_signal)
    _logger.info(f"Calibration done {duration=} {_TUNING_ITERATIONS=} {samples_per_sec=}")
    # At least 4 cycles in buffer for autocorrelation to make sense
    # Max frequency very safely below Nyquist = sample rate/2
    #  samples_per_sec/4 means 4 samples at least per cycle
    _logger.info(f"Frequency from {1/(duration/4)} to {samples_per_sec/4}")
    
    
@micropython.native
def _sample_adc( midi_note ):
    global adc_signal
    gc.collect()
    n = len( adc_signal )
    _logger.debug(f"Mic test mode {config.cfg["mic_test_mode"]=} {adc_device=}")
    if adc_device:
        # Sample the mic. This way of sampling has a bit of jitter but with the
        # algorithms used, the effect should be unnoticeable.
        read = adc_device.read
        t0 = ticks_us()
        for i in range(n):
            adc_signal[i] = read()
        duration = ticks_diff( ticks_us(), t0 )/1_000_000
    elif config.cfg["mic_test_mode"]:
        # Simulate a sine wave for testing

        freq = midi_note.frequency()*(1+0.02*(random.random()-0.5))
        sample_rate = 20000
        duration = n/sample_rate
        # amp from 500 to 2000. Emulate a 12 bit ADC with
        # values oscillating around 2048, so with that amp
        # values may go from 48 to 4048 (and can go from 0 to 4095)
        amp = random.randrange(500,2000)
        dt = 1/sample_rate
        for i in range(n):
            adc_signal[i] = int(sin( 6.28*dt*i*freq )*amp+2048)

            

    return duration, adc_signal

@micropython.native
def _normalize( signal ):
    # Normalize the signal
    avg = sum( signal )//len( signal )
    for i,x in enumerate( signal ):
        signal[i] = x - avg
        
    # Calculate amplitude as average of the max of several intervals
    maxsum = 0
    intervals = 5
    interval_start = 0
    interval_len = len(signal)//intervals
    mv = memoryview(signal)
    for i in range(intervals):
        interval_end = interval_start + interval_len
        maxsum += max( mv[interval_start:interval_end] )
        interval_start = interval_end
    amplitude = maxsum / intervals
    
    # Scale back to a low amplitude to avoid overflow during autocorrelation
    if amplitude != 0:
        for i, x in enumerate( signal ) :
            signal[i] = int( x/amplitude*128 )
    return amplitude, signal

@micropython.viper
def _autocorrelation_one_pass( signal:ptr32, lag:int, size:int ) -> int:
  # One step of autocorrelation
  sum_signal = 0
  n2 = lag
  for n1 in range(size-lag):
      sum_signal += signal[n1] * signal[n2]
      n2 += 1
  return sum_signal


@micropython.native
def _autocorrelate( signal ):
    global auto_signal
    # Do a autocorrelation of the signal, this filters noise
    size = len(signal)
    for i in range(size):
        auto_signal[i] = 0
    for lag in range(size):
        auto_signal[lag] += _autocorrelation_one_pass( signal, lag, size )
    return auto_signal

def _sample_normalize_filter_zcr( midi_note ):
    # Acquire signal, autocorrelate and then compute frequency
    duration, signal = _sample_adc( midi_note )
    amplitude, signal = _normalize( signal )
    auto_signal = _autocorrelate( signal )
    frequency = zcr.compute_frequency( auto_signal, duration )
    #print(f"snfz {midi_note=} {frequency=:.1f} {amplitude=:.1f} {duration=}")
    return frequency, amplitude, duration

    
async def get_note_pitch(  midi_note ):
    _logger.info(f"get_note_pitch {midi_note=}")
    
    freqlist = []
    amplist = []    
    solenoid.note_on( midi_note )
    # Wait for sound to stabilize before calling tuner
    await asyncio.sleep_ms(500)
    try:
        for iteration in range(_TUNING_ITERATIONS):
            frequency, amplitude, _ = _sample_normalize_filter_zcr( midi_note )
            freqlist.append( frequency )
            amplist.append( amplitude )
            cents = midi_note.cents( frequency )
            nominal = midi_note.frequency()
            _logger.info(f"get_note_pitch iteration {iteration=} {midi_note=} {nominal=:.1f} measured={frequency:.1f} {cents=:.1f}" )
            await asyncio.sleep_ms( 100 ) # yield, previous code was CPU bound
        _store_signal( midi_note  ) # Sample again and store last signal in flash
    except Exception as e:
        _logger.exc(e, "Exception in get_note_pitch")
    finally:
        solenoid.note_off( midi_note )

    frequency = sum( freqlist ) / len( freqlist )
    amplitude = sum( amplist ) / len( amplist )
    return frequency, amplitude, freqlist, amplist

def _get_stored_tuning( ):
    try:
        with open( config.ORGANTUNER_JSON, "r") as file:
            stored_tuning = json.load( file )
            
        # Keys are strings in json, but int needed here
        d = {}
        for k, v in stored_tuning.items():
            d[int(k)] = v
        return d
    except:
        # Make new organtuner_json file
        stored_tuning = {}
        for midi_note in pinout.all_valid_midis:
            d = {}
            d["name"] = str( midi_note )
            # >>> pending: eliminate cents, amp, keep centslist, amplist
            d["cents"] = -9999
            d["amp"] = 1
            d["centslist"] = [-9999]
            d["amplist"] = [1]
            d["pinname"] = solenoid.get_pin_name( midi_note )
            stored_tuning[hash(midi_note)] = d
        with open( config.ORGANTUNER_JSON, "w" ) as file:
            json.dump( stored_tuning, file )
        _logger.info(f"new {config.ORGANTUNER_JSON} written" )
    return stored_tuning

    # Change keys (midi_note) to integer type
    return dict(( (int(k),v) for k,v in stored_tuning.items() ))
    
async def _update_tuning( midi_note ):
    # Tune a note and update organtuner.json
    _logger.info(f"_update_tuning {midi_note}")
    await asyncio.sleep(1)
    freq, amp, freqlist, amplist = await get_note_pitch( midi_note )
    stored_tuning = _get_stored_tuning()
    h = hash( midi_note )
    stored_tuning[h]["cents"] = midi_note.cents( freq )
    stored_tuning[h]["amp"] = amp
    stored_tuning[h]["centslist"] = [ midi_note.cents( f )
                    for f in freqlist ] 
    stored_tuning[h]["amplist"] = amplist
    
    stored_tuning[h]["pinname"] = solenoid.get_pin_name( midi_note )
    with open( config.ORGANTUNER_JSON, "w" ) as file:
        json.dump( stored_tuning, file )
    _logger.info(f"_update_tuning {midi_note} stored in flash" )
        

def _store_signal( midi_note ):
    duration, signal = _sample_adc( midi_note )
    filename = "signal" +  str(midi_note) + ".tsv"
    with open(filename, "w") as file:
        s = str(duration).replace(".",",")
        file.write("\t\tduration\t" + s)
        for x in signal:
            file.write( str(x).replace(".",",") + "\n" )
    _logger.info(f"{filename} written")
            
     
def tune_all( ):
    for midi_note in pinout.all_valid_midis:
        queue_tuning( ( "tune", midi_note ) )


def queue_tuning( request ):
    #  Request is a pair of action name ("tune", "note_on", "note_repeat")
    # and MIDI note number for "tune" and "note_on"
    # The queue is served by the _organtuner_process.
    tuner_queue.append( request )
    start_tuner_event.set()
    start_tuner_event.clear()

async def sound_note( midi_note ) :
    for _ in range(8):
        # 8 quarter notes at a moderato 100 bpm       
        solenoid.note_on( midi_note )
        await asyncio.sleep_ms( 500 )
        solenoid.note_off( midi_note )
        await asyncio.sleep_ms( 100 )
        
async def repeat_note( midi_note ):
    initial_tempo = 60 # Let's start with quarter notes in a largo at 60 bpm
    fastest_note = 30 # 30 milliseconds seems to be a good lower limit on note duration
    play_during = 2000 # play during 2 seconds
    silence_percent = 10 # approximate percent of time assigned to a note
    minimum_silence = 30 # milliseconds, seems good limit
    tempo = initial_tempo
    while True:
        quarter = 60 / tempo * 1000
        if quarter < fastest_note:
            break
        note_duration = quarter * ( 1-silence_percent/100 )
        silence = max( minimum_silence, quarter * silence_percent/100 )
        _logger.debug(f"repeat note {note_duration=:.1f} {silence=:.1f}")
        t = 0
        while t <= play_during:
            solenoid.note_on( midi_note )
            await asyncio.sleep_ms( round(note_duration) )
            solenoid.note_off( midi_note )
            await asyncio.sleep_ms( round(silence) )
            t += note_duration + silence
        tempo *= 1.414 # double speed every 2
        await asyncio.sleep_ms( 500 ) # a bit of silence inbetween

async def scale_test( ):
    notelist = [ midi_note for midi_note in pinout.all_valid_midis ]
    notelist.sort( key=lambda m: m.hash )
    print("scale test notelist", notelist )
    for duration in [240, 120, 60, 30]: # In milliseconds
        for i in range(2):
            # Play twice: one up, one down
            for midi_note in notelist:
                solenoid.note_on( midi_note )
                await asyncio.sleep_ms( duration )
                solenoid.note_off( midi_note )
                await asyncio.sleep_ms( 30 )
            # alternate ascending and descending
            notelist.reverse()
        await asyncio.sleep_ms( 500 )    
  

async def _organtuner_processs( ):
    while True:
        await modes.wait_for_tuner_mode()
        try:
            if len( tuner_queue ) > 0:
                (request, midi_note ) = tuner_queue.pop(0)
                # Tuner queue can contain (request, integer hash)
                # or (request, Note )
                if type( midi_note ) is int:
                    print(f"Organtuner byhash {midi_note=} {midi_note//256=} {midi_note%256=}")
                    midi_note = midi.Note( byhash=midi_note )
                if request == "tune":
                    await _update_tuning( midi_note )
                elif request == "note_on":
                    await sound_note( midi_note )
                elif request == "note_repeat":
                    await repeat_note( midi_note )
                elif request == "scale_test":
                    await scale_test( )
                else:
                    raise RuntimeError( f"Organtuner request unknown: {request}") 
            else:
                # Queue empty, wait to be woken up
                await start_tuner_event.wait()
        except Exception as e:
            _logger.exc(e, "exception in _organtuner_processs")
        finally:
            pass

def pinout_changed():
    try:
        os.remove( config.ORGANTUNER_JSON )
    except:
        pass
    
_init()
