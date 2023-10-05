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



def _init( ):
    global logger, current_setlist,  setlist_task, touch_button
    global player_task, start_event, waiting_for_start_tune_event
    logger = getLogger( __name__ )
    touch_button = touchpad.TouchButton( pinout.touchpad_pin )
    
    current_setlist = []
    waiting_for_start_tune_event  = False
    
    setlist_task = asyncio.create_task( _setlist_process() )
    player_task = None

    # Register start event for tachometer and touch button
    # Webserver calls start_tune, instead of registering event
    # but all "start tune" methods converge on setting start_event
    start_event = asyncio.Event()
    tachometer.set_start_turning_event( start_event )
    touch_button.set_release_event( start_event )
    
    
    # Tell the player how to get the top tuneid. Player can't import setlist,
    logger.debug("init ok")
    

# Functions related to the different ways to start a tune   
def start_tune():
    # Called if start button on performance page is pressed
    start_event.set()
        
def wait_for_start():
    global waiting_for_start_tune_event
    start_event.clear()
    waiting_for_start_tune_event = True
    await start_event.wait()
    waiting_for_start_tune_event = False
        
def is_waiting():
    global waiting_for_start_tune_event
    return waiting_for_start_tune_event
                               
# The background setlist process - wait for start and play next tune              
async def _setlist_process():
    global current_setlist, player_task
    # When powered on, always load setlist
    load()

    while True:
        # Ensure loop will always yield
        await asyncio.sleep_ms(10)
       
        # Stall if in tuner or config mode
        await modes.wait_for_play_mode()
        
        # Wait for user to start tune
        
        await wait_for_start()
        
        # User signalled start of tune
        # Do we have a setlist?
        if len( current_setlist ) == 0:
            # No setlist: make a new setlist
            shuffle_all_tunes()
            logger.info(f"Automatic play, shuffle all tunes {len(current_setlist)}")
            # If tunelist is empty, there will be an exception below

        # Get top tune and play
        tune = current_setlist.pop(0)
        
        # Play tune in separate task
        logger.info(f"play tune will start {tune=}")
        player_task = asyncio.create_task( player.play_tune( tune ) )
        try:
            await player_task
        except:
            # Don't let player exceptions stop the setlist task.
            pass
        player_task = None
        
            
        logger.info(f"play_tune ended {player.get_progress()}" )

        # Wait for the crank to cease turning
        # after a tune has played
        if tachometer.is_installed():
            while tachometer.is_turning():
                await asyncio.sleep_ms( 100 )
        

# Setlist managment functinos: add/queue tune, start, stop, top, up, down,...        
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
    global player_task

    if (len(current_setlist) > 0 
        and player.get_progress()["tune"] == current_setlist[0]
       ):
        del current_setlist[0]
    
    if player_task:
        player_task.cancel()
    
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
    global current_setlist
    # Move this tune to top of setlist
    # Move to top
    s = current_setlist[pos]
    del current_setlist[pos]
    current_setlist.insert(0,s)
    
def drop( pos ):
    global current_setlist
    del current_setlist[pos]

    
def to_beginning_of_tune():
    global current_setlist
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

# The webserver get_progress() calls this function. 
# Integrate all the progress in one response.
def get_progress(  ):
    progress = player.get_progress()
    
    tachometer.complement_progress( progress )

    progress["setlist"] =  current_setlist
    if is_waiting():
        # If setlist is waiting for start, the player does not
        # know the current tune yet
        try:
            progress["tune"] = current_setlist[0]
        except IndexError:
            progress["tune"] = None
        progress["status"] = "waiting"
        progress["playtime"] = 0  
    return progress

_init()
