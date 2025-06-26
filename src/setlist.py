# (c) 2023 Hermann Paul von Borries
# MIT License
# Setlist control: setlist task, setlist management

import asyncio
from random import randrange

from drehorgel import config, tunemanager, crank, player, gpio, led
import touchpad
from minilog import getLogger
import fileops

# >>> could be interesting to have more stored setlist? not convinced
# >>> automatically created setlist?
# >>> add to setlist from history page?
# setlist_history.json = all tunes played today
# "Save" and "load" would need to ask for setlist. 
# Makes things more complicated...?

def del_key(key, dictionary):
    if key in dictionary:
        del dictionary[key]


class Setlist:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.current_setlist = [] # for now
        self.playback_enabled = True
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
        self.automatic_delay = config.get_int("automatic_delay")
        if self.automatic_delay:
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
        
    
    async def _wait_for_start( self ):

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

        while True:

            # Ensure this loop will always yield
            await asyncio.sleep_ms(100)

            # Wait for music to start (crank turns, or touch pad
            # was touched or web button or automatic playback or whatever)
            await self._wait_for_start()
            
            # Check if playback is still enabled.
            # Both pinout and organtuner can disable plabyack
            # to avoid interference with music playback.
            if not self.playback_enabled:
                # Exit loop. Only way to get back to playback
                # is to reboot.
                break

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
        self.logger.debug("Not in playback mode, setlist process exit")
        # Progress of current tune will not be updated anymore.




    # Setlist managment functions: add/queue tune, start, stop, top, up, down,...
    def queue_tune(self, tuneid):
        # If not in setlist: add
        # If in setlist: delete
        # Each tune may be only once in setlist
        changed = False
        if tuneid in self.current_setlist:
            i = self.current_setlist.index(tuneid)
            del self.current_setlist[i]
            del_key(tuneid, self.tune_requests)
            changed = True
        else:
            # Append to setlist. 
            self.current_setlist.append(tuneid)
            changed = True
        if changed:
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

        self.logger.debug(f"Setlist loaded {len(self.current_setlist)} elements")

    def clear(self):
        self.current_setlist = []
        self._write_current_setlist()

    def _get_pos(self, tuneid):
        # Get position of tuneid in current setlist
        # If not found, raise ValueError. 
        # This may happen if file added without using filemanager.
        # Or if page/tunelib needs refreshing in the browser.
        return self.current_setlist.index(tuneid) 

    def _interchange( self, pos1, pos2 ):
        # Interchange tunes at positions pos1 and pos2 of the setlist
        cs = self.current_setlist
        cs[pos1], cs[pos2] = cs[pos2], cs[pos1]
        self._write_current_setlist()

    def up(self, tuneid):  
        try:  
            pos = self._get_pos(tuneid)
            # Move this tune one up in setlist
            self._interchange( pos, pos - 1 )
        except (ValueError, IndexError):
            # _get_pos can raise ValueError if the element is not in setlist.
            # Example: delete, then move without updating page.
            # _interchange() can raise IndexError (same reason)
            # This will correct itself after the next refresh of the page.
            pass

    def down(self, tuneid):
        try:
            # Move this tune one down in setlist
            pos = self._get_pos(tuneid)
            self._interchange( pos, pos + 1 )
        except (ValueError, IndexError):
            pass

    def top(self, tuneid):
        # Move this tune to top of setlist
        try:
            pos = self._get_pos(tuneid)
            # Move to top
            s = self.current_setlist[pos]
            del self.current_setlist[pos]
            self.current_setlist.insert(0, s)
            self._write_current_setlist()
        except (ValueError, IndexError):
            pass

    def drop(self, tuneid):
        try:
            pos = self._get_pos(tuneid)
            del self.current_setlist[pos]
            self._write_current_setlist()
        except (ValueError, IndexError):
            pass

# >>> add bottom function?

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
        # Shuffle current setlist (no builtin shuffle)
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
        progress["automatic_delay"] = self.automatic_delay
        progress["playback_enabled"] = self.playback_enabled
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
        while self.playback_enabled:
            # Wait for any tune to ned
            while self.player_task:
                await asyncio.sleep_ms(500)
            # Wait the time between tunes as indicated in config.json
            await asyncio.sleep( self.automatic_delay )
            # If no tune playing, kick start event to get tune going
            if not self.player_task:
                self.logger.debug("Automatic playback sets music start event")
                self.music_start_event.set()

    async def _blink_empty( self ):
        while self.playback_enabled:
            led.set_blink_setlist( self._is_empty() )
            await asyncio.sleep_ms(370) # type:ignore

    def sync( self, tunelib ):
        for tuneid in set(self.current_setlist)-set(tunelib):
            self.drop( tuneid )

        stored_setlist = fileops.read_json(
                config.STORED_SETLIST_JSON,
                default=[])
        changed = False
        for tuneid in set(stored_setlist)-set(tunelib):
            del stored_setlist[stored_setlist.index(tuneid)]
            changed = True
        if changed:
            fileops.write_json(
                stored_setlist, config.STORED_SETLIST_JSON, keep_backup=False
            )

    def stop_playback( self ):
        # Called to stop playback of music immediately until the next reboot.
        # Organtuner: to avoid interference with tuning
        # Pinout: if pinout was changed to force user to reboot
        # Test pins (pinout.html): to avoid interference with pin testing
        if self.player_task:
            self.player_task.cancel() # type:ignore
            # If _setlist_process() is awaiting the  player_task,
            # the _setlist_process() will receive the CancelledError
            # and will abort.
            # If not, the variable self.playback_enabled set to False
            # will cause the _setlist_process() and other processes to exit

        # And prevent playing any more tunes
        # (if not this would interfere with tuning)
        # self.playback_enabled is tested by the different setlist processes
        # and these processes will exit.
        if self.playback_enabled:
            self.logger.debug("Playback disabled, setlist process will stop")
        self.playback_enabled = False
