# (c) 2023 Hermann Paul von Borries
# MIT License
# To allow mpremote mip install aioble on MAC:
# Go to Macintosh HD > Applications > Python3.11 folder
# (or whatever version of python you're using)
# Then double click on "Install Certificates.command"

import sys
import asyncio
import time
import json
import gc

from aioblemidi import Peripheral
import solenoid
from minilog import getLogger
import config
import modes

def _init( ): 
    global _logger, _ble_name, _status
    _logger = getLogger( __name__ )
    _ble_name = config.cfg["name"]
    
    
    # This status is queried by webserver to show activity
    _status = {
        "name": _ble_name,
        "advertising": False,
        "connected": False,
        "notesPlayed": False,
        "notesOmitted": False 
        }

    _logger.debug("init ok")
    
async def _blekeyboard_server( conn ):
    while True:
        await modes.wait_for_keyboard_mode()
        ts, event = await conn.get_wait()
        if len(event) >= 3 :
            esb = event[0] & 0xf0
            if event[0] == 0x80 or ( 
               event[0] == 0x90 and event[2] == 0):
                # Note off or note on with velocity=0
                note = event[1]
                solenoid.note_off( note )
            elif event[0] == 0x90 and event[2] != 0:
                # Note on
                note = event[1]
                if solenoid.exists( note ):
                    solenoid.note_on( note )
                    _status["notesPlayed"] += 1
                else:
                    _status["notesOmitted"] += 1
                
async def kbdprocess():
    while True:
        _status["advertising"] = True
        _status["connected"] = False
        async with Peripheral(_ble_name).connection() as conn:
            _status["advertising"] = False
            _status["connected"] = True
            keyboard_task = asyncio.create_task( _blekeyboard_server( conn ) )
        _status["connected"] = False
        keyboard_task.cancel()  

def get_status():
    return _status
    
_init()        
    
    


