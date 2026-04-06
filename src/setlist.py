# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# Setlist control: setlist task, setlist management

import asyncio
from random import randrange
import os

from drehorgel import config, tunemanager, crank, gpio, led, player

import touchpad
from minilog import getLogger
import fileops

def del_key(key, dictionary):
    if key in dictionary:
        del dictionary[key]

CURRENT_SETLIST = const(0)
STORED_SETLIST = const(1) 

MAX_SETLIST_SLOTS = const(10)

class Setlist:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.current_setlist = [] # for now

        self.playback_enabled = True
        self.waiting_for_start_tune_event = False

        # Any of these will set self.music_start_event:
        #   1. play.html page "start" button calling self.start_tune()
        #   2. touchpad up (if installed) triggering registered event
        #   3. crank starts to turn (if installed) triggering registered event
        #   4. time between tune elapsed (if automatic playback enabled) 
        
        self.music_start_event = asyncio.Event()
        crank.register_start_crank_event(self.music_start_event)
        # TouchButton acts correctly if gpio.touchpad_pin is not defined
        touch_button = touchpad.TouchButton(gpio.touchpad_pin)
        touch_button.register_up_event( self.music_start_event )

        # Dictionary of tune requests: key=tuneid, data=spectator name
        # Not in use.
        # self.tune_requests = {}

        # setlist_task: main task to process setlist.
        self.setlist_task = asyncio.create_task(self._setlist_process())
       
        if config.automatic_delay:
            # Task to start next tune after some seconds
            # if automatic delay was configured.
            self.automatic_playback_task = asyncio.create_task( self._automatic_playback_process(self.music_start_event) )

        # blink_empty_task: blink if setlist is empty
        self.blink_empty_task = asyncio.create_task( self._blink_empty() )
        # next_tune_task: touchpad+crank stopped=>next tune
        self.next_tune_task = asyncio.create_task( self._next_tune_process(touch_button) )
        # Handle of the player currently playing a tune.
        # If None, no tune is playing
        self.player_task = None
        self.logger.debug("init ok")


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
        return
    
    # The background setlist process - wait for start and play next tune
    async def _setlist_process(self):

        # Give start up some time
        await asyncio.sleep_ms(100)
        
        # When powered on, load setlist if present
        # First try with current setlist, if empty then
        # try with stored setlist.
        # For transition to new stored setlist names
        for slot, old_filename in enumerate(["/data/setlist_current.json","/data/setlist_stored.json" ]):
            try:
                os.rename( old_filename, self.stored_setlist_filename(slot) )
            except OSError:
                pass

        # Read current setlist, if empty load setlist 1
        self.load( CURRENT_SETLIST )
        # If empty, current setlist stays empty...
                  
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
                # Exit loop. Only way to get back to playback enabled
                # is to reboot.
                self.logger.debug("Not in playback mode, setlist process exit")
                return

            # User signalled start of tune
            # Get a current setlist by shuffling if no setlist
            if self.shuffle_if_empty():
                self.logger.info("Tunelib empty, setlist terminated")
                return

            # Get top tune and play
            tuneid = self.current_setlist.pop(0)
            self._save_current()

            led.start_tune_flash()
            # >>> delay play_tune if tunelib changes are being applied????
            # Play tune. Store task to have a handle
            # because we may need to cancel it on request (next tune
            # button or da capo button or playback disabled)
            self.player_task = asyncio.create_task( 
                player.play_tune(tuneid)
            )
            await self.player_task # type:ignore

            # Record that this task has ended and isn't available anymore
            self.player_task = None

            # Clean up tune_requests, delete all
            # elements not in setlist. It may be sufficent
            # if only this tuneid is deleted.
            #  not needed:
            #for t in self.tune_requests.keys():
            #    if t not in self.current_setlist:
            #        del_key(tuneid, self.tune_requests)

            # If velocity has been altered by software or by
            # encoder, reset to normal. User can change velocity
            # before the next tune starts.
            crank.set_velocity(50)
 



    # Setlist managment functions: add/queue tune, start, stop, top, up, down,...
    def queue_tune(self, tuneid, slot):
        # Should a tuneid that is not in the tunelib
        #  be added to a setlist, that will not matter much
        # since the browser will check setlist against her/his tunelib
        # and drop tuneids that are not in tunelib.
        if slot == 0:
            slist = self.current_setlist
        else:
            slist = self.load( slot, False )
        # If not in setlist: add
        # If in setlist: delete
        # Each tune may be only once in setlist
        changed = False
        # For slots 1 and up always append, never delete. But never append twice.
        # For slot 0 (current setlist), toggle.
        if tuneid in slist:
            # Case: tune in setlist
            if slot == 0:
                i = slist.index(tuneid)
                del slist[i]
                #del_key(tuneid, self.tune_requests)
                changed = True
        else:
            # Not in current setlist
            # Check if it is the current tune
            progress = player.get_progress()
            if tuneid == progress["tune"] and progress["status"] == "playing":
                # don't allow to queue the current tune again
                return
            # For all slots: if not in setlist, append
            slist.append(tuneid)
            changed = True
        if changed:
            self.save( slot, slist=slist )

    # tune_requests is not in use. self.tune_requests is {}
    # But support is there
    # def add_tune_requests(self, request_dict):
    #     self.tune_requests.update(request_dict)
    #     changed = False
    #     for tuneid in request_dict.keys():
    #         if tuneid not in self.current_setlist:
    #             self.current_setlist.append(tuneid)
    #             changed = True
    #     if changed:
    #         self._save_current()
        # current setlist is updated separately

    def stop_tune(self):
        # Called with the "next" button on play.html
        if (
            self.current_setlist and
            player.get_progress()["tune"] == self.current_setlist[0]
        ):
            # Delete from top of setlist
            #tuneid = self.current_setlist[0]
            del self.current_setlist[0]
            self._save_current()
            #del_key(tuneid, self.tune_requests)

        # Stop current tune, if playing
        if self.player_task:
            self.player_task.cancel() # type:ignore
            # Avoid cancelling while processing finally
            # if there are two stop_tune just one after the other
            self.player_task = None
            led.stop_tune_flash()
 

    def save(self, slot, slist=None ):
        # setlist 0 is written twice at start of tune?
        
        # >>> consider guarding with RequestSlice in webserver.py
        if not( 0 <= slot < MAX_SETLIST_SLOTS):
            raise ValueError

        # Save setlist in RAM to file
        filename = self.stored_setlist_filename( slot )
        fileops.write_json(
            slist or self.current_setlist, filename, keep_backup=False
        )

    def _save_current( self ):
        self.save( CURRENT_SETLIST )

    def load(self, slot, into_current=True):
        # >>> consider guarding with RequestSlice, better in webserver.py?
        # Read setlist from flash
        filename = self.stored_setlist_filename( slot )
        slist = fileops.read_json(filename, default=[])
        if into_current:
            self.current_setlist = slist
            self.logger.debug(f"Setlist {slot} loaded {len(self.current_setlist)} tunes")
            self._save_current()
        return slist
    
    def clear(self):
        self.current_setlist = []
        self._save_current()

    def _get_pos(self, tuneid):
        # Get position of tuneid in current setlist
        # If not found, raise ValueError. 
        # This may happen if file added without using filemanager.
        # Or if page/tunelib needs refreshing in the browser.
        return self.current_setlist.index(tuneid) 

    def _interchange( self, pos1, pos2 ):
        n = len(self.current_setlist)
        if ( 0 <= pos1 < n and
             0 <= pos2 < n ):
            # Interchange tunes at positions pos1 and pos2 of the setlist
            cs = self.current_setlist
            cs[pos1], cs[pos2] = cs[pos2], cs[pos1]
            self._save_current()

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
            self._save_current()
        except (ValueError, IndexError):
            pass

    def drop(self, tuneid):
        try:
            pos = self._get_pos(tuneid)
            del self.current_setlist[pos]
            self._save_current()
        except (ValueError, IndexError):
            pass

    def bottom(self, tuneid):
        # Move this tune to bottom of setlist
        try:
            pos = self._get_pos(tuneid)
            # Move to bottom
            s = self.current_setlist[pos]
            del self.current_setlist[pos]
            self.current_setlist.append(s)
            self._save_current()
        except (ValueError, IndexError):
            pass

    def to_beginning_of_tune(self):
        # Restart current tune, called by "da capo"
        # button on play.html
        progress = player.get_progress()
        tuneid = progress["tune"]
        if tuneid:
            self.stop_tune()
            self.current_setlist.insert(0, tuneid)
            self._save_current()

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
        self._save_current()

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
        # progress["tune_requests"] = {} # self.tune_requests # >>> can be dropped
        progress["automatic_delay"] = config.automatic_delay
        progress["playback_enabled"] = self.playback_enabled
        if self.waiting_for_start_tune_event:
            # If setlist is waiting for start, the player does not
            # know the current tune yet
            try:
                progress["tune"] = self.current_setlist[0]
            except IndexError:
                progress["tune"] = None
            progress["status"] = "waiting"
            progress["playtime"] = 0

    def _no_tunes(self):
        # No setlist and nothing playing nor about to play
        return not self.current_setlist and self.player_task == None

    async def _automatic_playback_process( self, music_start_event ):
        self.logger.debug("Automatic playback enabled")
        # Organtuner and pinout tests can stop this
        while self.playback_enabled:
            # Wait the time between tunes as indicated in config.json
            # but not less than the minimum explained in config.html
            await asyncio.sleep( max(5,config.automatic_delay ))
            # If no tune playing, kick start event to get next tune going
            if not self.player_task:
                music_start_event.set()
            # Wait for tune to end
            while self.player_task:
                await asyncio.sleep_ms(500)


    async def _blink_empty( self ):
        while self.playback_enabled:
            led.set_blink_setlist( not self.current_setlist )
            await asyncio.sleep_ms(1000) # type:ignore

    # >>> Revisit need of setlist.sync()
    # >>> Javascript is already guarding itself against unsync'ed setlists
    def sync( self, tunelib ):
        # setlist.sync is not strictly necessary since javascript
        # layer checks if setlist's tuneids are in tunelib.
        for slot in range(MAX_SETLIST_SLOTS):
            stored_setlist = self.load( slot, False )
            # self.load() will return [] if file does not exist
            delete = set(stored_setlist)-set(tunelib)
            for tuneid in delete:
                del stored_setlist[stored_setlist.index(tuneid)]
            if delete:
                self.save( slot, slist=stored_setlist )
                if slot == CURRENT_SETLIST:
                    # And reload from stored
                    self.load( CURRENT_SETLIST )

    def stop_playback( self ):
        # Called to stop playback of music immediately until the next reboot.
        # Organtuner: to avoid interference with tuning
        # Pinout: if pinout was changed to force user to reboot
        # Test pins (pinout.html): to avoid interference with pin testing
        if self.player_task:
            self.player_task.cancel() # type:ignore
            self.player_task = None
            # If _setlist_process() is awaiting the  player_task,
            # the _setlist_process() will receive the CancelledError
            # and will abort.

        # And prevent playing any more tunes
        # self.playback_enabled is tested by the different setlist processes
        # and these processes will exit.
        if self.playback_enabled:
            self.logger.debug("Playback disabled, setlist process will stop")
        self.playback_enabled = False

    def stored_setlist_filename( self, slot ):
        # used by mcserver
        return f"{config.DATA_FOLDER}setlist_stored_{slot}.json"
    
    def get_titles( self ):
        if config.multiple_setlists:
            # returns slot 1-(MAX_SETLIST_SLOTS-1), title, number of tunes
            # The "titles file" has MAX_SETLIST_SLOTS elements. 
            # Element 0 is the "current setlist" and is skipped here.
            titles =  fileops.read_json( config.SETLIST_TITLES_JSON, default=["current", "","", "","","","","","",""])
            # [slot_number, title, number of tunes in setlist]
            return [ [slot,title, len(self.load(slot,False))]
                    for slot, title in enumerate(titles)
                    if slot >= 1]
        # Single stored setlist enabled. Signal this to javascript
        # using an empty title list.
        return []
    
    def save_titles( self, titles ):
        # User changed titles using browser.
        if len(titles) != MAX_SETLIST_SLOTS:
            raise ValueError
        fileops.write_json( titles, config.SETLIST_TITLES_JSON, keep_backup=False )
    
    async def _next_tune_process( self, touch_button ):
        tpevent = asyncio.Event()
        # register_up_event supports many registered events.
        touch_button.register_up_event( tpevent )
        while True:
            while not self.player_task:
                await asyncio.sleep_ms(200)
            # Touch while playing cancels tune
            tpevent.clear()
            while self.player_task:
                if tpevent.is_set():
                    if crank.is_installed():
                        if not crank.is_turning():
                            self.stop_tune()
                    else:
                        self.stop_tune()
                await asyncio.sleep_ms(200)

    def get_top( self ):
        # For tunemanager.
        progress = player.get_progress()
        if tuneid := progress.get("tune"):
            return tuneid
        if self.current_setlist:
            return self.current_setlist[0]