# (c) 2023 Hermann Paul von Borries
# MIT License
# Setlist control: setlist task, setlist management

import asyncio
from random import randrange

import scheduler
from drehorgel import config, tunemanager, crank, player, gpio, led
import touchpad
from minilog import getLogger
import fileops

# >>> blink soft blue while setlist is empty.

def del_key(key, dictionary):
    if key in dictionary:
        del dictionary[key]


class Setlist:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.current_setlist = [] # for now

        self.waiting_for_start_tune_event = False

        # Any of these will set self.music_start_event:
        #   1. play.html page start button calling self.start_tune()
        #   2. touchpad up (if installed) triggering registered event
        #   3. crank starts to turn (if installed) triggering registered event
        #   4. time between tune elapsed (if automatic playback enabled) 
        
        # 300 ms after crank start event: crank turns are already stable
        self.music_start_event = asyncio.Event()
        crank.register_start_crank_event(self.music_start_event)
        touch_button = touchpad.TouchButton(gpio.touchpad_pin)
        touch_button.register_up_event( self.music_start_event )

        # Dictionary of tune requests: key=tuneid, data=spectator name
        # Will ony be used if mcserver module is present.
        self.tune_requests = {}

        self.setlist_task = asyncio.create_task(self._setlist_process())
        self.automatic_playback_task = asyncio.create_task( self._automatic_playback_process() )
        self.blink_empty_task = asyncio.create_task( self._blink_empty() )
        self.player_task = None
        self.timeout_task = None
        self.logger.debug("init ok")


    def _write_current_setlist( self ):
        # Write current setlist to flash to make
        # it persistent across reboots.
        fileops.write_json( 
            self.current_setlist, 
            config.CURRENT_SETLIST_JSON,
            keep_backup=False)

    # Functions related to the different ways to start a tune
    def start_tune(self):
        # Called by webserver if start button on performance page is pressed
        self.music_start_event.set()
        # Reset "tempo follows crank" if started by web button
        # Perhaps the crank isn't working? This is safer!
        player.set_tempo_follows_crank(False)
        
    
    async def wait_for_start( self ):

        # Record that we are waiting for tune to start
        # for progress.
        self.waiting_for_start_tune_event = True
        self.music_start_event.clear()
        await self.music_start_event.wait() # type:ignore

        self.waiting_for_start_tune_event = False

        # Cancel automatic playback timeout task, if running, so it won't
        # interfere later (timeout task is for automatic play only)
        if self.timeout_task:
            self.timeout_task.cancel() # type:ignore
            self.timeout_task = None
        return

    def is_waiting_for_tune_start(self):
        # waiting_for_start_tune_event is set only
        # while waiting for tune to start
        return self.waiting_for_start_tune_event

    # The background setlist process - wait for start and play next tune
    async def _setlist_process(self):

        # Give start up some time
        await asyncio.sleep_ms(100)
        
        # When powered on, load setlist if present
        # First try with current setlist, if empty then
        # try with stored setlist.
        for filename in (config.CURRENT_SETLIST_JSON,
                         config.STORED_SETLIST_JSON):
            self.current_setlist = fileops.read_json( filename, default=[] )
            if self.current_setlist:
                break    

        while scheduler.is_playback_enabled():

            # Ensure this loop will always yield
            await asyncio.sleep_ms(100)

            # Wait for music to start
            await self.wait_for_start()
            
            # User signalled start of tune
            # Get a current setlist by shuffling if no setlist
            if self.shuffle_if_empty():
                self.logger.info("Tunelib empty, setlist terminated")
                return

            # Get top tune and play
            tuneid = self.current_setlist.pop(0)
            self._write_current_setlist()

            self.logger.info(f"start {tuneid=}")
            led.start_tune_flash()

            # Play tune. Store task to have a handle
            # because we may need to cancel it on request (next tune
            # button or da capo button)
            self.player_task = asyncio.create_task( 
                player.play_tune(tuneid, tuneid in self.tune_requests)
            )
            await self.player_task # type:ignore
            
            # Record that this task has ended and isn't available anymore
            self.player_task = None
            self.logger.info(f"ended {tuneid=}")


            # Clean up tune_requests, delete all
            # elements not in setlist. It may be sufficent
            # if only this tuneid is deleted.
            for t in self.tune_requests.keys():
                if t not in self.current_setlist:
                    del_key(tuneid, self.tune_requests)

            # Wait for the crank to cease turning after
            # a tune has played before proceeding to next tune.
            # If no crank, this will never wait.
            await crank.wait_stop_turning()

            # If velocity has been altered by software or by
            # encoder, reset to normal. User can change velocity
            # before the next tune starts.
            crank.set_velocity(50)
    
        # If tuner or test mode are active, don't
        # interfere playing music. Rebooting resets this mode.
        # However, if a tune is playing, the user would have
        # to stop that manually.
        # This is to avoid interference between MIDI files
        # (player.py)
        # and the tuning process (organtuner.py)
        self.logger.debug("Not in playback mode, stop setlist process")
        # Progress of current tune will not be updated anymore.




    # Setlist managment functions: add/queue tune, start, stop, top, up, down,...
    def queue_tune(self, tuneid):
        # If not in setlist: add
        # If in setlist: delete
        # Each tune may be only once in setlist
        if tuneid in self.current_setlist:
            i = self.current_setlist.index(tuneid)
            del self.current_setlist[i]
            del_key(tuneid, self.tune_requests)
        else:
            self.current_setlist.append(tuneid)
        self._write_current_setlist()

    def add_tune_requests(self, request_dict):
        self.tune_requests.update(request_dict)
        changed = False
        for tuneid in request_dict.keys():
            if tuneid not in self.current_setlist:
                self.current_setlist.append(tuneid)
                changed = True
        if changed:
            self._write_current_setlist()
        # current setlist is updated separately

    def stop_tune(self):
        # Called with the "next" button on play.html
        if (
            not self._is_empty()
            and player.get_progress()["tune"] == self.current_setlist[0]
        ):
            # Delete from top of setlist
            tuneid = self.current_setlist[0]
            del self.current_setlist[0]
            self._write_current_setlist()
            del_key(tuneid, self.tune_requests)

        # Stop current tune, if playing
        if self.player_task:
            self.player_task.cancel() # type:ignore
            led.stop_tune_flash()

    def save(self):
        # Save current setlist to another file
        fileops.write_json(
            self.current_setlist, config.STORED_SETLIST_JSON, keep_backup=False
        )
        # >>>spectator_list is not made persistent. Tough luck.

    def load(self):
        # Read setlist from flash
        self.current_setlist = fileops.read_json(
                config.STORED_SETLIST_JSON,
                default=[])
        self._write_current_setlist()
        self.logger.debug(f"Setlist loaded {len(self.current_setlist)} elements")

    def clear(self):
        self.current_setlist = []
        self._write_current_setlist()

    def _interchange( self, pos1, pos2 ):
        # Interchange tunes at positions pos1 and pos2
        cs = self.current_setlist
        cs[pos1], cs[pos2] = cs[pos2], cs[pos1]
        self._write_current_setlist()

    def up(self, pos):
        # Move this tune one up in setlist
        self._interchange( pos, pos - 1 )

    def down(self, pos):
        # Move this tune one down in setlist
        self._interchange( pos, pos + 1)

    def top(self, pos):
        # Move this tune to top of setlist
        # Move to top
        s = self.current_setlist[pos]
        del self.current_setlist[pos]
        self.current_setlist.insert(0, s)
        self._write_current_setlist()

    # >>> add bottom() function?


    def drop(self, pos):
        del self.current_setlist[pos]
        self._write_current_setlist()

    def to_beginning_of_tune(self):
        # Restart current tune, called by "da capo"
        # button on play.html
        progress = player.get_progress()
        tuneid = progress["tune"]
        if tuneid:
            self.stop_tune()
            self.current_setlist.insert(0, tuneid)
            self._write_current_setlist()

    def shuffle(self):
        # Shuffle current setlist
        # Fisher-Yates shuffle https://en.wikipedia.org/wiki/Random_permutation
        permutation = self.current_setlist
        n = len(permutation)
        for i in range(n-1):
            j = randrange(i,n) # A random integer such that i ≤ j < n
            # Swap the randomly picked element with permutation[i]
            t = permutation[i]
            permutation[i] = permutation[j]
            permutation[j] = t
        self._write_current_setlist()

    def shuffle_all_tunes(self):
        # Make a new setlist with all tunes and shuffle
        # Must get a deep copy of tunelib to self.current_setlist
        # if not tunemanager._tuneids will be emptied while playing....
        self.current_setlist = tunemanager.get_autoplay()
        self.shuffle()
        led.shuffle_all_flash()

    def shuffle_3stars(self):
        # See shuffle_all_tunes for comments
        self.current_setlist = tunemanager.get_autoplay_3stars()
        self.shuffle()
        led.shuffle_all_flash()

    def shuffle_if_empty(self):
        if self._no_tunes():
            self.shuffle_3stars()
            if self._no_tunes():
                # No "3 stars" marked tunes, shuffle all:
                self.shuffle_all_tunes()
        return self._no_tunes()

    # The webserver get_progress() calls this function.
    def complement_progress(self, progress):
        progress["setlist"] = self.current_setlist
        progress["tune_requests"] = self.tune_requests
        if self.is_waiting_for_tune_start():
            # If setlist is waiting for start, the player does not
            # know the current tune yet
            try:
                progress["tune"] = self.current_setlist[0]
            except IndexError:
                progress["tune"] = None
            progress["status"] = "waiting"
            progress["playtime"] = 0

    def _is_empty(self):
        # Setlist empty?
        return not self.current_setlist
    
    def _no_tunes(self):
        # No setlist and nothing playing nor about to play
        return self._is_empty() and self.player_task == None

    async def _automatic_playback_process( self ):
        timeout_seconds = config.get_int("automatic_delay") or 0
        if not timeout_seconds:
            return 
        while scheduler.is_playback_enabled():
            # Wait for any tune to ned
            while self.player_task:
                await asyncio.sleep_ms(500)
            # Wait the time between tunes as indicated in config.json
            await asyncio.sleep( timeout_seconds )
            # If no tune playing, kick start event to get tune going
            if not self.player_task:
                self.logger.debug("Automatic playback sets music start event")
                self.music_start_event.set()

    async def _blink_empty( self ):
        while True:
            led.set_blink_setlist( self._is_empty() )
            await asyncio.sleep_ms(300) # type:ignore

