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


def del_key(key, dictionary):
    if key in dictionary:
        del dictionary[key]


class Setlist:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.touch_button = touchpad.TouchButton(gpio.touchpad_pin)
        self.clear()
        self.waiting_for_start_tune_event = False

        # Register start event for tachometer and touch button
        # Webserver calls start_tune, instead of registering event
        # but all "start tune" methods converge on setting self.start_event
        # 500 ms == crank turns are already stable
        self.start_event = crank.register_event(500)
        # Make touch button release do the same as start turning crank
        self.touch_button.register_up_event(self.start_event)
        
        # Event to know when bored turning the crank and nothing happens
        self.shuffle_event = crank.register_event(3000)
        # Make touch button double click to the same as cranking a lot of time
        self.touch_button.register_double_event(self.shuffle_event)
                
        # Dictionary of tune requests: key=tuneid, data=spectator name
        # Will ony be used if mcserver module is present.
        self.tune_requests = {}

        
        self.setlist_task = asyncio.create_task(self._setlist_process())
        self.shuffle_task = asyncio.create_task(self._shuffle_process())
        self.player_task = None

        self.logger.debug("init ok")

    # Functions related to the different ways to start a tune
    def start_tune(self):
        # Called by webserver if start button on performance page is pressed
        self.start_event.set()

    def wait_for_start(self):

        # For TouchPad and Web: Clear to get rid of previous value. 
        # TouchPad and Web must set this event starting now. Previous set event
        # are disregarded.
        # For crank: if the crank is turning, this event will be set very shortly.
        # If the crank is not turning, wait....
        self.start_event.clear()
        self.waiting_for_start_tune_event = True
        await self.start_event.wait()
        self.waiting_for_start_tune_event = False

    def is_waiting(self):
        return self.waiting_for_start_tune_event

    # The background setlist process - wait for start and play next tune
    async def _setlist_process(self):
        # When powered on, always load setlist
        self.load()

        while True:
            # Ensure loop will always yield
            await asyncio.sleep_ms(100)

            # Wait for user to start tune
            await self.wait_for_start()

            # If tuner or test mode are active, don't
            # interfere playing music. Reloading the
            # page restores control.
            if not scheduler.is_playback_mode():
                self.logger.debug("Not in play mode")
                continue

            # User signalled start of tune
            # Do we have a setlist?
            if len(self.current_setlist) == 0:
                # No setlist, do nothing
                continue

            # Get top tune and play
            tuneid = self.current_setlist.pop(0)

            # Play tune in separate task

            self.logger.info(f"play tune will start {tuneid=}")
            self.player_task = asyncio.create_task(
                player.play_tune(tuneid, tuneid in self.tune_requests)
            )
            try:
                await self.player_task
            except Exception as e: 
                # Don't let player exceptions stop the setlist task.
                # Player should have handled/reported the exception
                self.logger.exc( repr(e), "Unhandled exception in player_task")
            self.player_task = None

            # Clean up tune_requests, delete all
            # elements not in setlist. It may be sufficent
            # if only this tuneid is deleted.
            for t in self.tune_requests.keys():
                if t not in self.current_setlist:
                    del_key(tuneid, self.tune_requests)

            self.logger.info("play_tune ended")

            # Wait for the crank to cease turning
            # after a tune has played before proceeding to next tune.
            await crank.stop_turning_event.wait()
   

    async def _shuffle_process(self):
        # Process to wait for a shuffle event:
        #       long time turning crank
        #       double touch of touch pad
        # Web interface "shuffle all" button calls 
        # shuffle_all_tunes directly, no checking of empty setlist.
        while True:
            self.shuffle_event.clear()
            await self.shuffle_event.wait()
            if len(self.current_setlist) == 0:
                self.shuffle_all_tunes()
            await asyncio.sleep_ms(100)
                

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
            len(self.current_setlist) > 0
            and player.get_progress()["tune"] == self.current_setlist[0]
        ):
            # Delete from top of setlist
            tuneid = self.current_setlist[0]
            del self.current_setlist[0]
            del_key(tuneid, self.tune_requests)

        # Stop current tune, if playing
        if self.player_task:
            self.player_task.cancel()

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

        self.logger.debug(f"Setlist loaded {self.current_setlist=}")

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

    # The webserver get_progress() calls this function.
    def complement_progress(self, progress):
        progress["setlist"] = self.current_setlist
        if self.is_waiting():
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
        return len(self.current_setlist) == 0
    
setlist = Setlist()
