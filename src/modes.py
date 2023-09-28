
import asyncio
import time
import config
import scheduler

from minilog import getLogger

_mode = "play"

def _init( ):
    global _logger, _mode 
    _logger = getLogger(__name__)
    _logger.debug("init start")

    change_mode( "play" )  

    _logger.debug("init ok")

def is_valid_mode( newmode ):
    return newmode in config.cfg["modes"]

def change_mode( newmode, password=None ):
    global _mode

    if not is_valid_mode( newmode ):
        return False 

    if _mode != "play":
        # Lazy import, as late as possible
        # Scheduler only works for play mode
        scheduler.run_always()

    if newmode == "config":
        if config.verify_password( password ):
            _mode = "config"
            _logger.debug("enter_config_mode password ok, mode changed to config")
            return True
        else:
            return False

    _mode = newmode

 

    _logger.debug(f"Mode changed to {_mode}")

def is_play_mode():
    return _mode == "play"

def is_keyboard_mode():
    return _mode == "keyboard"

def is_tuner_mode():
    return _mode == "tuner"

async def wait_for_mode( ismode ):
    # Stall until the appropriate mode is active
    while True:
        if ismode():
            return
        await asyncio.sleep_ms( 1000 )
        
async def wait_for_play_mode():
    await wait_for_mode( is_play_mode )

async def wait_for_tuner_mode():
    await wait_for_mode( is_tuner_mode )

async def wait_for_keyboard_mode():
    await wait_for_mode( is_keyboard_mode )

def get_mode():
    return _mode

    
 
_init()

