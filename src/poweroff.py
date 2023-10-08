# (c) 2023 Hermann Paul von Borries
# MIT License
# Power off task. Monitors activity and enters deepsleep to save battery
# if not active.
import machine
import asyncio
import player
from minilog import getLogger
import config
import modes
import led
import webserver


def _init():
    global _power_task, _logger
    _logger = getLogger( __name__ )
    _power_task = asyncio.create_task( power_process() )
    _logger.debug("init ok")

async def power_process():
    _logger.debug("Power off monitor started")
    last_tune = None
    last_playtime = None
    idle_minutes = 0
    idle_deepsleep_minutes = config.get_int("idle_deepsleep_minutes", 15)
    try:
        while True:
            await asyncio.sleep( 60 ) # Sleep for 1 minute and check.
            
            progress = player.get_progress()
            playtime = progress["playtime"]
            tune = progress["tune"]
            # Any activity in the last minute?
            if ( playtime != last_playtime or
                 tune != last_tune or
                 webserver.is_active() ):
                # Yes, reset time
                idle_minutes = 0
            else:
                idle_minutes += 1
                _logger.debug(f"Idle for {idle_minutes} minutes limit {idle_deepsleep_minutes}")

            last_tune = tune
            last_playtime = playtime
            
            if idle_minutes > idle_deepsleep_minutes:
                led.off()
                _logger.info("Idle for {idle_minutes} minutes, entering deepsleep")
                await asyncio.sleep_ms(100)
                machine.deepsleep()
                
    except Exception as e:
        _logger.exc( e, "power management process not aborted")
            

def shutdown():
    _power_task.cancel()
    _logger.info("Poweroff process stopped")

_init()
