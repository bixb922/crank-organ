import json
import asyncio
import time
import gc
from random import randrange

from minilog import getLogger
import config
import tunelist
import tachometer
import player
import modes
import pinout
import touchpad
import solenoid

web_button_event = asyncio.Event()

def start_tune():
    # Called if start button on performance page is pressed
    web_button_event.set()

wait_for_tune_flag = False
def wait_for_tune( max_msec=None ):
    global wait_for_tune_flag
    web_button_event.clear()
    touch_button.release_event.clear()
    tachometer.clear()
    wait_for_tune_flag = True
    t0 = time.ticks_ms()
    while True:
        if ( tachometer.is_turning() or 
            touch_button.release_event.is_set() or
            web_button_event.is_set()
           ):
            wait_for_tune_flag = False
            return True
        # Process timeout if specified
        if max_msec and time.ticks_diff( time.ticks_ms(), t0 ) > max_msec:
            return False
        await asyncio.sleep_ms( 10 )

def is_waiting():
    return wait_for_tune_flag
                               
def _init( ):
    global logger, current_setlist, stop_player_event, setlist_task, touch_button
    logger = getLogger( __name__ )
    touch_button = touchpad.TouchButton( pinout.touchpad_pin )
    
    current_setlist = []
    stop_player_event = asyncio.Event()
    setlist_task = asyncio.create_task( _setlist_process() )
    # Tell the player how to get the top tuneid. Player can't import setlist,
    logger.debug("init ok")
    
    
async def _setlist_process():
    global current_setlist, stop_player_event
    # When powered on, always load setlist
    load()
    skip_wait_for_tune = False
    while True:
        # Ensure loop will always yield
        await asyncio.sleep_ms(10)
        await modes.wait_for_play_mode()
        if len( current_setlist ) > 0:
            if not skip_wait_for_tune:
                await wait_for_tune()
            skip_wait_for_tune = False
            # Get top tune and play
            tune = current_setlist.pop(0)
            stop_player_event.clear()
            logger.info(f"play tune will start {tune=}")
            await player.play_tune( tune, stop_player_event )
            logger.info(f"play_tune ended {player.get_progress()}" )
            # Wait for turning the crank to cease 
            # after a tune has played
            if tachometer.is_installed():
                while tachometer.is_turning():
                    await asyncio.sleep_ms( 100 )
                    
        else:   
            # Wait for max 1 second. If there is an attempt to start a tune
            # and no setlist then shuffle all. If wait for tune
            # gives timeout, try again later.
            # >>> REVISAR WAIT FOR TUNE, HACE LO QUE SE REQUIERE?
            if await wait_for_tune( 1000 ):
                # Id we want to start tune and there is no tune, shuffle all.
                logger.info(f"Automatic play, shuffle all tunes {len(current_setlist)}, clap 3")
                # Shuffle all tunes to make setlist.
                # Check again if empty, changes may have occurred during
                # await wait_for_tune()
                if len( current_setlist ) == 0:
                    shuffle_all_tunes()
                    # We already got "start", don't wait again
                    skip_wait_for_tune = True

                                   
def get_current_setlist():
    return current_setlist
        
def queue_tune( tune ):
    # If not in setlist: add
    # If in setlist: delete
    # Each tune may be only once in setlist
    if tune in current_setlist:
        i = current_setlist.index(tune)
        del current_setlist[i]
    else:
        current_setlist.append( tune )
        # _setlist_process will poll current_setlist periodically

    
def stop_tune():
    # Stop current tune
    global stop_player_event

    if (len(current_setlist) > 0 
        and player.get_progress()["tune"] == current_setlist[0]
       ):
        del current_setlist[0]
    stop_player_event.set()
    
def save():
    # Save curent setlist to flash
    global current_setlist
    with open( config.SETLIST_JSON, "w") as file:
        json.dump( current_setlist, file )
    
def load():
    # Read setlist from flash
    global current_setlist
    try:
        with open( config.SETLIST_JSON, "r") as file:
            current_setlist = json.load( file )
        # _setlist_process will poll current_setlist periodically
    except:
        current_setlist = []
        
    logger.debug(f"Setlist loaded {current_setlist=}")

def clear():
    global current_setlist
    current_setlist = []
    
def up( pos ):
    # Move this tune one up in setlist
    global current_setlist
    # Move one position up
    s = current_setlist[pos]
    del current_setlist[pos]
    current_setlist.insert(pos-1,s)

    
def down( pos ):
    # Move this tune one down in setlist
    global current_setlist
    # Move one position down
    s = current_setlist[pos]
    del current_setlist[pos]
    current_setlist.insert(pos+1,s)

    
def top( pos ):
    # Move this tune to top of setlist
    # Move to top
    s = current_setlist[pos]
    del current_setlist[pos]
    current_setlist.insert(0,s)
    
def drop( pos ):
    del current_setlist[pos]

    
def to_beginning_of_tune():
    # Restart current tune
    tune = player.get_progress()["tune"]
    if tune:
        stop_tune()
        current_setlist.insert( 0, tune )
        

def shuffle():
    # Shuffle setlist 
    global current_setlist
    setlist = current_setlist
    current_setlist = []
    while len(setlist) > 0:
        i = randrange( 0, len(setlist ) )
        queue_tune( setlist[i] )
        del setlist[i]

    
def shuffle_all_tunes():
    global current_setlist
    # Make a new setlist with all tunes and shuffle
    # Must get a deep copy of tunelist to current_setlist
    # if not tunelist._tuneids will be emptied while playing....
    current_setlist = list( tunelist.get_autoplay() )
    shuffle()

def get_top_tuneid():
    global current_setlist
    if current_setlist:
        return current_setlist[0] 
    else:
        return None 


_init()
