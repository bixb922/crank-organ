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


def del_key(key, dictionary):
    if key in dictionary:
        del dictionary[key]


class Setlist:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.touch_button = touchpad.TouchButton(gpio.touchpad_pin)
        self.current_setlist = [] # for now

        self.waiting_for_start_tune_event = False

        # Any of these will set self.music_start_event:
        #   play.html page start button via self.start_tune()
        #   touchpad up (if installed) via registered event
        #   crank starts to turn (if installed) via registered event
        #   time between tune elapsed (if automatic playback) via self.automatic_playback()
        
        # 300 ms after crank start event: crank turns are already stable
        self.music_start_event = crank.register_event(300)

        # Event to know when bored turning the crank and nothing happens,
        # (losing patience takes 3 seconds??? this is a fast world)
        self.shuffle_event = crank.register_event(3000)

        # Make touch button double click to the same as cranking for a longer time
        # i.e. make it shuffle all
    
        # Dictionary of tune requests: key=tuneid, data=spectator name
        # Will ony be used if mcserver module is present.
        self.tune_requests = {}

        self.setlist_task = asyncio.create_task(self._setlist_process())
        self.shuffle_task = asyncio.create_task(self._shuffle_all_process())
        self.touchdown_task = asyncio.create_task(self._touchdown_process())
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
        # Perhaps the crank isn't working, this is safer
        player.set_tempo_follows_crank(False)
        
    
    async def wait_for_start( self ):

        self.music_start_event.clear()

        # Record that we are waiting for tune to start
        # for progress.
        self.waiting_for_start_tune_event = True
        await self.music_start_event.wait()
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

        # Let powerup finish
        await asyncio.sleep_ms(10)
        
        # When powered on, load setlist if present
        # First try with current setlist, if empty then
        # try with stored setlist.
        for filename in (config.CURRENT_SETLIST_JSON,
                         config.STORED_SETLIST_JSON):
            self.current_setlist = fileops.read_json( filename, default=[] )
            if self.current_setlist:
                break    

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
                self.logger.debug("Not in playback mode")
                # Could as well return, there is currently no way
                # to return to playback mode except reboot.
                # This is to avoid interference between MIDI files
                # (player.py)
                # and the tuning process (organtuner.py)
                # No led blinks, this is not a problem... its avoiding one.
                continue

            # User signalled start of tune
            # Do we have a setlist?
            if self.isempty():
                self.logger.debug("No setlist, do nothing")
                # No setlist, do nothing
                continue

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
            await self.player_task 
            
            # Record that this task has ended and isn't available anymore
            self.player_task = None

            # Clean up tune_requests, delete all
            # elements not in setlist. It may be sufficent
            # if only this tuneid is deleted.
            for t in self.tune_requests.keys():
                if t not in self.current_setlist:
                    del_key(tuneid, self.tune_requests)

            self.logger.info(f"ended {tuneid=}")

            # Wait for the crank to cease turning after
            # a tune has played before proceeding to next tune.
            # If no crank, this will not cause waiting
            await crank.wait_stop_turning()
            # If velocity has been altered by software or by
            # encoder, reset to normal. User can change velocity
            # before the next tune starts.
            crank.set_velocity(50)
    

    async def _shuffle_all_process(self):
        # This process tests if 
        # crank turns a long time, or the touchpad is
        # pressed twice. If so, all tunes are shuffled
        # but only if setlist is empty.
        
        # Note that the shuffle event is triggered
        # every time the crank starts, but since
        # there is a test for "self.no tunes()", that 
        # does not lead to a problem
        while True:
            await asyncio.sleep_ms(100) # Avoid tight CPU bound loop
            self.shuffle_event.clear()
            await self.shuffle_event.wait()
            if self.no_tunes():
                # There is no risk of "shuffle twice in a row"
                # because now the setlist is not empty anymore
                # (except if there are no tunes...)
                self.shuffle_3stars()
                if self.is_empty():
                    self.shuffle_all_tunes()
    
    async def _touchdown_process(self):
        # Process to detect touchpad up.
        # Will cancel a tune if detected while playing a tune.
        # Will start a tune while waiting for tune to start

        # Count number of touch with empty setlist and no tune waiting
        touch_count = 0
        touchpad_up_event = asyncio.Event()
        self.touch_button.register_up_event( touchpad_up_event )
        while True:
            await asyncio.sleep_ms(500)

            touchpad_up_event.clear()
            await touchpad_up_event.wait()

            # Two touches when no setlist will shuffle all
            if self.no_tunes():
                touch_count += 1
            else:
                touch_count = 0
            if touch_count >= 2:
                self.logger.debug("_touchdown_process shuffle")
                self.shuffle_event.set()

            # One touch will start current tune (if any)
            if self.is_waiting_for_tune_start():
                # User signalled start of tune with touchpad
                self.logger.debug("_touchdown_process start tune")
                # And signal tune to start
                self.music_start_event.set()


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
            not self.isempty()
            and player.get_progress()["tune"] == self.current_setlist[0]
        ):
            # Delete from top of setlist
            tuneid = self.current_setlist[0]
            del self.current_setlist[0]
            self._write_current_setlist()
            del_key(tuneid, self.tune_requests)

        # Stop current tune, if playing
        if self.player_task:
            self.player_task.cancel()
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

    def up(self, pos):
        # Move this tune one up in setlist
        # Move one position up
        s = self.current_setlist[pos]
        del self.current_setlist[pos]
        self.current_setlist.insert(pos - 1, s)
        self._write_current_setlist()

    def down(self, pos):
        # Move this tune one down in setlist
        # Move one position down
        s = self.current_setlist[pos]
        del self.current_setlist[pos]
        self.current_setlist.insert(pos + 1, s)
        self._write_current_setlist()

    def top(self, pos):
        # Move this tune to top of setlist
        # Move to top
        s = self.current_setlist[pos]
        del self.current_setlist[pos]
        self.current_setlist.insert(0, s)
        self._write_current_setlist()

    # >>> add bottom() ?
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

    def isempty(self):
        # Setlist empty?
        return not self.current_setlist
    
    def no_tunes(self):
        # No setlist and nothing playing nor about to play
        return self.isempty() and self.player_task == None

    def automatic_playback( self ):
        # do the automatic playback based on "automatic_delay"
        # parameters of config.json.

        async def automatic_playback_delay( timeout_seconds ):
            if self.no_tunes():
                self.shuffle_event.set()
            await asyncio.sleep( timeout_seconds )
            self.music_start_event.set()
            self.timeout_task = None
            # In automatic mode, tempo doesn't follow crank
            # because there is probably no manual crank
            player.set_tempo_follows_crank(False)

        timeout_seconds = config.get_int("automatic_delay", 0)
        # Check if "automatic play with a pause" has been asked for
        if timeout_seconds > 0:
                
            self.logger.debug(f"Automatic playback after {timeout_seconds} seconds")
            # Start tune after delay, no user action necessary
            # But touchpad, crank, will preempt user action.
            self.timeout_task = asyncio.create_task( automatic_playback_delay(timeout_seconds) )
            # The timeout_task is also cancelled in self.wait_for_start()
            # 