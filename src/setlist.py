# (c) 2023 Hermann Paul von Borries
# MIT License
# Setlist control: setlist task, setlist management

import asyncio
from random import randrange

import scheduler
from config import config
from tunemanager import tunemanager
from tachometer import crank
from player import player
from pinout import gpio
import touchpad
from minilog import getLogger
import fileops
from led import led


def del_key(key, dictionary):
    if key in dictionary:
        del dictionary[key]

import time


class Setlist:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.touch_button = touchpad.TouchButton(gpio.touchpad_pin)
        self.clear()
        self.waiting_for_start_tune_event = False

        # Any of these will set self.start_event:
        #   play.html page start button via self.start_tune()
        #   touchpad up (if installed) via registered event
        #   crank starts to turn (if installed) via registered event
        #   time between tune elapsed (if automatic playback) via self.automatic_playback()
        
        # 50 ms after crank start event: crank turns are already stable
        self.start_event = crank.register_event(50)

         # Event to know when bored turning the crank and nothing happens,
        # (losing patience takes 3 seconds?)
        self.shuffle_event = crank.register_event(3000)

        # Make touch button double click to the same as cranking a lot of time 
        # i.e. make it shuffle all
        self.touch_button.register_double_event(self.shuffle_event)
    
        # Dictionary of tune requests: key=tuneid, data=spectator name
        # Will ony be used if mcserver module is present.
        self.tune_requests = {}

        self.setlist_task = asyncio.create_task(self._setlist_process())
        self.shuffle_task = asyncio.create_task(self._shuffle_all_process())
        self.touchdown_task = asyncio.create_task(self._touchdown_process())
        self.player_task = None
        self.timeout_task = None
        self.logger.debug("init ok")


    # Functions related to the different ways to start a tune
    def start_tune(self):
        # Called by webserver if start button on performance page is pressed
        self.start_event.set()
        # Reset "tempo follows crank" if started by web button
        # Perhaps the crank isn't working, this is safer
        player.set_tempo_follows_crank(False)
        
    
    async def wait_for_start( self ):

        self.start_event.clear()

        # Record that we are waiting for tune to start
        # for progress.
        self.waiting_for_start_tune_event = True
        await self.start_event.wait()
        self.waiting_for_start_tune_event = False
        # Cancel timeout task, if any, so it won't
        # interfere later
        if self.timeout_task:
            self.timeout_task.cancel()
            self.timeout_task = None
        return

    def is_waiting_for_tune_start(self):
        # waiting_for_start_tune_event is set only
        # while waiting for tune to start
        return self.waiting_for_start_tune_event

    # The background setlist process - wait for start and play next tune
    async def _setlist_process(self):
        # When powered on, always load stored setlist (if any)
        self.load()

        while True:
            # Ensure this loop will always yield
            await asyncio.sleep_ms(100)

            # add a timeout to wait_for_start if automatic playback
            self.automatic_playback()
           
            await self.wait_for_start()

            # If tuner or test mode are active, don't
            # interfere playing music. Reloading the
            # page restores control. Playback mode is activated
            # when navigating to play.html or tunelist.html and
            # disactivated with other pages.
            if not scheduler.is_playback_mode():
                self.logger.debug("Not in play mode")
                continue

            # User signalled start of tune
            # Do we have a setlist?
            if self.isempty():
                self.logger.debug("No setlist, do nothing")
                # No setlist, do nothing
                continue

            # Get top tune and play
            tuneid = self.current_setlist.pop(0)

            self.logger.info(f"play_tune will start {tuneid=} {tuneid in self.tune_requests=}")
            led.start_tune_flash()

            # Play tune. Create task because we may need to cancel it on request 
            self.player_task = asyncio.create_task( 
                player.play_tune(tuneid, tuneid in self.tune_requests)
            )
            await self.player_task 
            self.logger.debug("play_tune task ended")
            # Record that this task has ended and isn't available anymore
            self.player_task = None

            # Clean up tune_requests, delete all
            # elements not in setlist. It may be sufficent
            # if only this tuneid is deleted.
            for t in self.tune_requests.keys():
                if t not in self.current_setlist:
                    del_key(tuneid, self.tune_requests)

            self.logger.info("play_tune ended")

            # Wait for the crank to cease turning after
            # a tune has played before proceeding to next tune.
            # If no crank, this will not cause waiting
            await crank.wait_stop_turning()
    

    async def _shuffle_all_process(self):
        # This process tests if 
        # crank turns a long time, or the touchpad is
        # pressed twice. If so, all tunes are shuffled
        # but only if setlist is empty.
        
        # Note that the shuffle event is triggered
        # every time the crank starts, but since
        # there is a test for "no tunes", that 
        # does not lead to a problem
        while True:
            self.shuffle_event.clear()
            await self.shuffle_event.wait()
            if self.no_tunes():
                self.shuffle_all_tunes()
            await asyncio.sleep_ms(100)

    async def _touchdown_process(self):
        # Process to detect touchpad up.
        # Will cancel a tune if detected while playing a tune.
        # Will start a tune while waiting for tune to start
        touchpad_down_event = asyncio.Event()
        self.touch_button.register_up_event( touchpad_down_event )
        while True:
            touchpad_down_event.clear()
            await touchpad_down_event.wait()
            # See what to do with this event
            if self.is_waiting_for_tune_start():
                # Why did user start with touchpad?
                # Perhaps crank not working? Disable 
                # temporarily following crank.
                self.logger.debug("_touchdown_process start tune")
                player.set_tempo_follows_crank( False )
                # And signal tune to start
                self.start_event.set()
            elif self.player_task:
                # Touchpad while playing music will stop current tune
                self.logger.debug("_touchdown_process stop tune")
                self.stop_tune()
            else:
                # Well, this may happen, ignore
                self.logger.debug("_touchdown_process ignore")
            # Get rid of some contact bouncing and
            # ignore second click of double-clicks
            await asyncio.sleep_ms(round(touchpad.DOUBLE_TOUCH_MAX*1.2))


    # Setlist managment functions: add/queue tune, start, stop, top, up, down,...
    def queue_tune(self, tuneid):
        # If not in setlist: add
        # If in setlist: delete
        # Each tune may be only once in setlist
        # Each tune may be only once in setlist
        if tuneid in self.current_setlist:
            i = self.current_setlist.index(tuneid)
            del self.current_setlist[i]
            del_key(tuneid, self.tune_requests)
        else:
            self.current_setlist.append(tuneid)

    def add_tune_requests(self, request_dict):
        self.tune_requests.update(request_dict)
        for tuneid in request_dict.keys():
            if tuneid not in self.current_setlist:
                self.current_setlist.append(tuneid)
        # current setlist is updated separately

    def stop_tune(self):
        if (
            not self.isempty()
            and player.get_progress()["tune"] == self.current_setlist[0]
        ):
            # Delete from top of setlist
            tuneid = self.current_setlist[0]
            del self.current_setlist[0]
            del_key(tuneid, self.tune_requests)

        # Stop current tune, if playing
        if self.player_task:
            self.player_task.cancel()
            led.stop_tune_flash()

    def save(self):
        # Save curent setlist to flash
        fileops.write_json(
            self.current_setlist, config.SETLIST_JSON, keep_backup=False
        )
        # spectator_list is transient, do not store

    def load(self):
        # Read setlist from flash
        try:
            self.current_setlist = fileops.read_json(config.SETLIST_JSON)
            # _setlist_process will poll self.current_setlist periodically
        except (OSError, ValueError):  # No setlist.
            self.clear()

        self.logger.debug(f"Setlist loaded {len(self.current_setlist)} elements")

    def clear(self):
        self.current_setlist = []

    def up(self, pos):
        # Move this tune one up in setlist
        # Move one position up
        s = self.current_setlist[pos]
        del self.current_setlist[pos]
        self.current_setlist.insert(pos - 1, s)

    def down(self, pos):
        # Move this tune one down in setlist
        # Move one position down
        s = self.current_setlist[pos]
        del self.current_setlist[pos]
        self.current_setlist.insert(pos + 1, s)

    def top(self, pos):
        # Move this tune to top of setlist
        # Move to top
        s = self.current_setlist[pos]
        del self.current_setlist[pos]
        self.current_setlist.insert(0, s)

    def drop(self, pos):
        del self.current_setlist[pos]

    def to_beginning_of_tune(self):
        # Restart current tune
        progress = player.get_progress()
        tuneid = progress["tune"]
        if tuneid:
            self.stop_tune()
            self.current_setlist.insert(0, tuneid)

    def shuffle(self):
        # Shuffle setlist
        setlist = self.current_setlist
        self.clear()
        while len(setlist) > 0:
            i = randrange(0, len(setlist))
            self.queue_tune(setlist[i])
            del setlist[i]

    def shuffle_all_tunes(self):
        # Make a new setlist with all tunes and shuffle
        # Must get a deep copy of tunelib to self.current_setlist
        # if not tunemanager._tuneids will be emptied while playing....
        self.current_setlist = list(tunemanager.get_autoplay())
        self.shuffle()
        led.shuffle_all_flash()

    # The webserver get_progress() calls this function.
    def complement_progress(self, progress):
        progress["setlist"] = self.current_setlist
        if self.is_waiting_for_tune_start():
            # If setlist is waiting for start, the player does not
            # know the current tune yet
            try:
                progress["tune"] = self.current_setlist[0]
            except IndexError:
                progress["tune"] = None
            progress["status"] = "waiting"
            progress["playtime"] = 0
            progress["tune_requests"] = self.tune_requests
        return progress
    
    def isempty(self):
        # Setlist empty?
        return len(self.current_setlist) == 0
    
    def no_tunes(self):
        # No setlist and nothing playing nor about to play
        return self.isempty() and self.player_task == None

    def automatic_playback( self ):
        # Enable automatic playback based on "automatic_delay"
        # parameters of config.json.

        async def on_timeout( timeout_seconds ):
            await asyncio.sleep( timeout_seconds )
            self.start_event.set()
            self.timeout_task = None
            # In automatic mode, tempo doesn't follow crank
            # because there is probably no manual crank
            player.set_tempo_follows_crank(False)

        timeout_seconds = config.get_int("automatic_delay", 0)
        if timeout_seconds > 0:
            if self.no_tunes():
                self.shuffle_all_tunes()
            self.logger.debug(f"Automatic playback after {timeout_seconds} seconds")
            # Start tune after delay, no user action necessary
            # But touchpad, crank, will preempt user action.
            self.timeout_task = asyncio.create_task( on_timeout(timeout_seconds) )
            # The timeout_task is also cancelled in
            # self.wait_for_start()
                
setlist = Setlist()
