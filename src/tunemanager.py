# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
# Manages tune library.
from micropython import const
import os
import asyncio
import hashlib
from random import random
import time

import scheduler
from minilog import getLogger
import fileops
from drehorgel import timezone

# >>> print setlist with lyrics
# >>> print simple setlist (order, title, time)
# >>> print complete setlist (author, genre, year, info, rating)
# >>> add play midi button to tunelibedit?

# original hash
# def _compute_hash(s):
#     # Each tune has a unique hash derived from the filename
#     # This is the tuneid. By design it is made unique (see _make_unique_hash)
#     # and stable.
#     digest = hashlib.sha256(fileops.filename_no_gz(s).encode()).digest()
#     folded_digest = bytearray(6)
#     i = 0
#     for n in digest:
#          folded_digest[i] ^= n
#          i = (i + 1) % 6 # 6 = len(folded_digest)
#     hash = binascii.b2a_base64(folded_digest).decode()
#     # Make result compatible with URL encoding
#     return "i" + hash.replace("\n", "").replace("+", "-").replace("/", "_")

import sys
if sys.implementation.version[1] < 26: # type:ignore
    print(">>>MicroPython version not supported", sys.implementation )
# >>> Viper function _fold_digest() does not work correctly previous to 1.26

def _compute_hash(filename_no_gz):
    # Compute hash for midi filename (.gz must be stripped before calling)
    digest = hashlib.sha256(filename_no_gz.encode()).digest()
    return _fold_digest( digest, len(digest) ).decode() # type:ignore

b64encoding = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
# Preallocated bytearrays for the _fold routine
base64_buffer = bytearray(9)
folded_buffer = bytearray(8) # Only first 6 used
@micropython.viper # type:ignore
def _fold_digest( digest:ptr8, digest_len:int)->object: # type:ignore
    # Fold digest into 6 bytes
    folded = ptr8(folded_buffer) # type:ignore
    fz = ptr32(folded_buffer) # type:ignore
    fz[0] = 0 # shorter this way to set 8 bytes to 0
    fz[1] = 0

    i = 0
    p = 0
    pdigest = ptr8(digest) # type:ignore
    while p < digest_len:
        folded[i] ^= pdigest[p]
        i = (i + 1) % 6 # index from 0 to 5
        p += 1
    # To base 64, but translate these characters: "+" to "-" and "/" to "_"
    # The result can be used in a URL
    encoding = ptr8(b64encoding) # type:ignore
    b64 = ptr8(base64_buffer) # type:ignore
    b64[0] = 105 # ord("i"), tuneid hash keys start with that letter
    # >>> b64[1]=something does not work prior to MicroPyton 1.26!!!!
    # >>> but b64[0] works....
    b64[1] = encoding[  folded[0]>>2]                         # 0:765432
    b64[2] = encoding[((folded[0]&0x03)<<4) | (folded[1]>>4)] # 0:10 + 1:7654
    b64[3] = encoding[((folded[1]&0x0f)<<2) | (folded[2]>>6)] # 1:3210 + 2:76
    b64[4] = encoding[  folded[2]&0x3f ]                      # 2:564210

    b64[5] = encoding[  folded[3]>>2 ]                        # 3:765432
    b64[6] = encoding[((folded[3]&0x03)<<4) | (folded[4]>>4)] # 3:10 + 4:7654
    b64[7] = encoding[((folded[4]&0x0f)<<2) | (folded[5]>>6)] # 4:3210 + 5:76
    b64[8] = encoding[  folded[5]&0x3f ]                      # 5:564210
    return base64_buffer
  

# Define Tunelib Column names
# Must be equal to common.js
# tunelib.json entries are lists to get a smaller tunelib.json file

TLCOL_ID = const(0) 
TLCOL_TITLE = const(1)
TLCOL_GENRE = const(2)
TLCOL_AUTHOR = const(3)
TLCOL_YEAR = const(4)
TLCOL_TIME = const(5)
TLCOL_FILENAME = const(6)
TLCOL_AUTOPLAY = const(7) 
TLCOL_INFO = const(8)
TLCOL_DATEADDED = const(9) 
TLCOL_RATING = const(10)
TLCOL_SIZE = const(11) 
TLCOL_HISTORY = const(12)
TLCOL_LYRICS = const(13) # 1=there are lyrics, 0=no lyrics
TLCOL_COLUMNS = const(14)


# change_queue operation types
TLOP_FILE_UPDATE = const(1)
TLOP_FILE_DELETE = const(2)
TLOP_REPLACE_FIELD = const(3) # see common.js SetlistMenu class
TLOP_SYNCALL = const(4)

class TuneManager:
    def __init__(self, tunelib_folder, tunelib_filename, lyrics_filename, sync_filename ):
        # tunelib_folder: /tunelib, also could be /sd/tunelib
        # tunelib_filename: data/tunelib.json
        # lyrics_json: data/lyrics.json 
        # sync_filename: If not there: no sync pending.
        #             If it contains [], sync checks all files
        #             If it contains a non-empty list, sync check all queued files.
        # This file is set when the filemanager detects upload of a MIDI file to the tunelib folder.
        self.tunelib_folder = tunelib_folder
        self.tunelib_filename = tunelib_filename
        self.lyrics_filename = lyrics_filename
        self.sync_filename = sync_filename
        self.logger = getLogger(__name__)        
        self.tunelib_progress = "Tunelib update not started"
        self.sync_task = asyncio.create_task(self._sync_process())
        self.sync_event = asyncio.Event()
        self.tunelib_signature = ""

        # Create tunelib.json and lyrics.json if not there.
        # to make javascript happy. Checking if file exists 
        # before reading could cut boot time by 2 seconds if there
        # are 1500 MIDI files.
        ly = self._read_lyrics() 
        tu = self._read_tunelib()
        self.logger.debug(f"init ok, {len(tu)} tunes in {tunelib_filename}, {len(ly)} lyrics in {lyrics_filename}")

    def _compute_tunelib_signature( self, tunelib ):
        # A number that changes (well, almost always) when the tunelib changes.
        # This is used as a very efficient method
        # to detect changes in the tunelib.json file.
        # Disregard TLCOL_HISTORY for hash because it does not mean a significant change.
        # Add 1 to allow browser distinguish between "empty tunelib" and
        # "no information about tunelib"=0
        self.tunelib_signature = sum( sum(hash(x) for i,x in enumerate(tune) if i!=TLCOL_HISTORY)  
                                for tune in tunelib.values() ) + 1
        
    def _read_tunelib(self):
        tunelib = fileops.read_json(self.tunelib_filename,
                                 default={},
                                recreate=True)
        # Check if some tunelib entry is in a very, very old format...
        for tuneid, tune in tunelib.items():
            if not tuneid.startswith("i") or len(tuneid) != 9:
                self.logger.info(f"Tuneid incorrect, removing tunelib entry for {tuneid} {tune[TLCOL_FILENAME]} {tune[TLCOL_TITLE]}, must sync")
                # Must sync and fill this entry again
                del tunelib[tuneid]
            # Fill columns if some very old format
            while len(tune) < TLCOL_COLUMNS:
                tune.append("")

        self._compute_tunelib_signature( tunelib )
        return tunelib
    
    def _write_tunelib_json(self, tunelib):
        self._compute_tunelib_signature( tunelib )
        fileops.write_json(tunelib, self.tunelib_filename, keep_backup=True)
    
    def _read_lyrics( self ):
        return fileops.read_json( self.lyrics_filename, 
                                 default={}, 
                                 recreate=True )

    def get_info_by_tuneid(self, tuneid):
        # Used by player.py to get tune info
        tunelib = self._read_tunelib()
        if tuneid not in tunelib:
            return None, 0
        filename = self.tunelib_folder + tunelib[tuneid][TLCOL_FILENAME]
        duration = tunelib[tuneid][TLCOL_TIME]
        return filename, duration
        
    def get_tune_count(self):
        tunelib = self._read_tunelib()
        count = len(tunelib)
        del tunelib
        return count

    def get_autoplay(self, rating=""):
        # Return list of all possible tune ids marked as autoplay.
        # used for setlist  shuffle all 
        # If rating="": include all tunes with autoplay.
        # If rating is "*", "**" or "***"
        # include all tuning with autoplay and specified rating or better.
        # The resulting list must be a copy, since it will be modified.
        tunelib = self._read_tunelib()
        return [
            tuneid for tuneid, v in tunelib.items() 
            if v[TLCOL_AUTOPLAY] and rating in v[TLCOL_RATING] ]

    def get_autoplay_3stars(self):
        return self.get_autoplay("***")


    def start_sync(self):
        # This is used by webserver.py when the tunelibedit.html
        # page has loaded so queue a "complete sync" operation
        # >>> do a TLOP_SYNCALL only if button is pressed?
        self._queue_change( [TLOP_SYNCALL,0,0,0])
        # and kick _sync_process() to start it right now!
        # since user is waiting for page to load
        self.sync_event.set()
        self._sync_progress("Start sync, please wait", type="start")

    def _sync_progress( self, msg, type="" ):
        # Show sync progress both on browser (if called by browser)
        # and on logger.
        # If not called from browser, self.tunelib_progress will not be used
        # (nobody cares)
        if type == "start":
            # Start sync, clear progress
            self.tunelib_progress = "" 
        elif type == "end":
            # Signal browser that sync is finished
            # by adding a special end marker
            msg = "***end***"
        self.tunelib_progress += msg + "<br>"
        self.logger.info( msg )

    def get_sync_progress( self ):
        # For webserver
        return self.tunelib_progress

    async def _wait_a_bit(self):
        # If sync is taking too long, yield CPU to other tasks
        # but sometimes only... not too frequently
        if random()>0.8:
            # On ESP32, minimum time to wait is 10 or 20 msec
            # anyhow...
            await asyncio.sleep_ms(10)

    def _dedup_midi_files( self, filedict ):
        # >>> move dedup to sync_one_file?. 
        # If file is .gz, then check for .mid
        # If both file.mid and foo.mid.gz are present,
        # erase foo.mid and keep foo.mid.gz
        # Make a copy of the filedict allows changing original
        for filename in list( 
                filename for filename in filedict.keys()
                if fileops.get_equivalent(filename) in filedict 
                and not fileops.is_compressed( filename )):
            self.logger.info(f"Dedup: erase file {filename}, duplicate with .gz")
            os.remove( self.tunelib_folder + filename )
            del filedict[filename]

    def _get_duration(self, filename):
        try:
            # Get duration in milliseconds
            return fileops.open_midi(self.tunelib_folder + filename).length_us() // 1000
        except Exception as e:
            self.logger.exc(e, f"Computing duration of {filename}")
            return 0
       
    
    def _sync_one_file( self, newtunelib, op, filename, filesize ):
        operation = ""
        tuneid, filename = self._make_unique_hash(filename, newtunelib)

        if op == TLOP_FILE_DELETE:
            try:
                del newtunelib[tuneid]
            except KeyError:
                self.logger.info(f"File {filename} was already removed from tunelib.json")
                return # No change
            return "Deleting entry"
        

        # Is it a new tune or a tune update?
        tune:list = newtunelib.get(tuneid)
        if tune is None:
            # New tune
            operation = "Adding"
            tune = [""] * TLCOL_COLUMNS
            newtunelib[tuneid] = tune
            tune[TLCOL_ID] = tuneid
            # Title based on filename
            tune[TLCOL_TITLE] = ("~" + fileops.get_filename_stem(filename)).replace("-", " ").replace("_"," ").replace("  "," ")
            tune[TLCOL_AUTOPLAY] = True
            tune[TLCOL_INFO] = self._get_initial_info( tune[TLCOL_TITLE] )
        # Update only if different name or different size.
        # Different name with same tuneid can happen with xxx.mid and xxx.mid.gz
        # because these two are considered equal.
        elif filesize == tune[TLCOL_SIZE] and filename == tune[TLCOL_FILENAME]:
            return # no change
        else:
            operation = "Updating"

        # Update tune info both for updated and new files
        tune[TLCOL_SIZE] = filesize
        tune[TLCOL_DATEADDED] = timezone.now_ymd()
        # This can take some time!!! (up to 3 seconds per tune)
        tune[TLCOL_TIME] = self._get_duration(filename)
        # Update filename, the file could now
        # have (or not) a .gz suffix and be different from before
        tune[TLCOL_FILENAME] = filename
        return operation

    async def _sync_process(self):
        while True:
            # self.sync_event is set when:
            # - tunelibedit.html is loaded
            # - a field or set of fields are changed with self.safe()
            # Also this code
            # will wake up anyhow every few
            # seconds and process whatever has been accumulated.
            # The timeout of wait_for() is in seconds
            try:
                await asyncio.wait_for( self.sync_event.wait(), 10 ) # type:ignore
            except asyncio.TimeoutError:
                pass
            if not self.sync_event.is_set():
                # If we got here without a kick (i.e. by timeout),
                # check if the
                # sync_filename is too fresh to do something.
                try:
                    file_stat = os.stat(self.sync_filename)
                except OSError:
                    # "file not found" means: nothing pending
                    continue

                # if file is young, wait a bit, unless file contains only
                # an empty list [], in that case sync all files right away.
                # This allows to process many files in one go (i.e. much faster)
                # when doing uploads. This time should be a bit larger than
                # the time it takes to ship changes on the tunelibedit.html page
                # and more than the time it takes to upload a file.
                if file_stat[6] > 2 and (time.time() - file_stat[8]) < 12:
                    self.logger.debug( f"Sync file is too young, waiting for next cycle" )
                    continue 
            self.sync_event.clear()
            # Don't sync during playback of music.
            # Let changes accumulate until playback stops.
            await scheduler.wait_for_player_inactive()

            await self._sync_now()

    async def _sync_now(self):
        await asyncio.sleep_ms(20) # let browser catch up
        # By default log to flash.
        changed = False
        newtunelib = self._read_tunelib()
        change_queue = self._read_sync_file()
        await asyncio.sleep_ms(20) # let browser catch up

        # If there is a "sync all" in change_queue, then queue all files
        if any((tlop[0]==TLOP_SYNCALL for tlop in change_queue)):
            # Must do a complete refresh
            # Compare tunelib.json with tunelib/*.mid
            # and update tunelib.json.
            self._sync_progress( "Listing files in tunelib folder" )
            # Yield CPU for a bit to allow webserver and other processes to run
            await asyncio.sleep_ms(20)
            # Make a dict with key=filename and data=file size (bytes)
            filedict = {direntry[0]: direntry[3] 
                    for direntry in os.ilistdir(self.tunelib_folder)
                    if fileops.get_file_type( direntry[0] ) == "mid"
                }
            # Remove duplicate files 
            # i.e. delete one if both aaa.mid and aaa.mid.gz present
            self._dedup_midi_files( filedict )
            await asyncio.sleep_ms(50)
            # Queue all existing files to see if some sync'ing is needed
            change_queue.extend( (TLOP_FILE_UPDATE, fn, size,0) for fn, size in filedict.items() )
            # and queue all files that have been deleted
            change_queue.extend( (TLOP_FILE_DELETE, tune[TLCOL_FILENAME],-1,0) 
                                for tune in newtunelib.values() 
                                if tune[TLCOL_FILENAME] not in filedict )
        await asyncio.sleep_ms(50) # let browser catch up
        for op, p1,p2,p3 in change_queue:
            if op == TLOP_FILE_UPDATE or op == TLOP_FILE_DELETE:
                # [TLOP_FILEUPDATE, p1:filename, p2:filesize, 0 ]
                # [TLOP_FILEDELETE, p1:filename, 0, 0 ]
                # _sync_one_file() handles all cases: add, update and delete
                operation = self._sync_one_file( newtunelib, op, p1, p2  )
                if operation:
                    changed = True
                    self._sync_progress( f"{operation} {p1} in tunelib.json" )
                    await asyncio.sleep_ms(100)
            elif op == TLOP_REPLACE_FIELD:
                # Change data field in tunelib.json
                # [TLOP_FIELD, p1:tuneid, p2:tlcol, p3:new_value]
                try:
                    # Update tunelib fields. queue_tunelib_change() already
                    # checked that p2 is a valid column number
                    self._update_tlop_field( newtunelib, p1, p2, p3 )
                    self.logger.debug(f"queued change applied ok, tuneid={p1} tcol={p2} new data={p3}]")
                    changed = True
                except KeyError:
                    self.logger.info(f"queued change not applied, tuneid={p1} not found")
            # Ignore other types, they may be
            # TLOP_SYNCALL that already has been processed
            # or may be a old format entry where a filename
            # is in this position. Just ignore, must do a sync all.

        changed = changed or self._sync_lyrics( newtunelib  )
        await asyncio.sleep_ms(50)

        # Check that setlist has only valid tuneids
        from drehorgel import setlist 
        setlist.sync( newtunelib )
        await asyncio.sleep_ms(50)
        if changed:
            self._write_tunelib_json(newtunelib)
            self._sync_progress("tunelib.json updated" )
        # delete all changes that were processed this time
        # There may be more changes in the queue that were
        # queued AFTER _sync_now() started
        stored_queue = self._read_sync_file()
        del stored_queue[0:len(change_queue)]

        self._write_sync_file(stored_queue)
        
        # Last element of tunelib_progress MUST contain
        # ***end*** for javascript in browser to know
        # that process has ended.
        
        self._sync_progress( "", type="end" )
        
    def _update_tlop_field( self, newtunelib, tuneid, tlcol, new_value ):
        # May raise KeyError if tuneid not in newtunelib
        # tlcol was checked in queue_field_changes()
        newtunelib[tuneid][int(tlcol)] = new_value

    def _make_unique_hash(self, path, newtunelib):
        fn = path.split("/")[-1]
        fn_no_gz = fileops.filename_no_gz(fn)
        #  .gz is not part of the hash
        # Make a collision-less hash for each file. The probability
        # of collisions is nil after a few iterations.
        for _ in range(3):
            tuneid = _compute_hash(fn_no_gz)
            tune = newtunelib.get(tuneid, None)
            # If new tune or if existing tune with correct filenames, return
            if not tune or fileops.filename_no_gz(tune[TLCOL_FILENAME]) == fn_no_gz:
                return tuneid, fn
            # Here either:
            #   a) it's a new tune
            #   b) the tunelib entry corresponds to another filename,
            #   i.e. it is a hash collision (probability of b) is near nil)
            # Collision. Probability is near nil, of the 
            # order of 2**(-48), repeating 3 times means
            # probability near 2**(-144) after mangling the filename
            
            # Mangle filename to get another hash
            newfn = fn.replace(".", "_.", 1)
            self.logger.info( f"Hash collision, renaming {fn} to {newfn}, lucky day" )
            # Change filename to avoid hash collisions...
            os.rename(self.tunelib_folder + fn, self.tunelib_folder + newfn)
            fn = newfn
            # Now hash function should be one-to-one, no collisions
        return tuneid, fn

    def queue_field_changes(self, update):
        # Called from tunelibedit.html with dictionary of changed
        # fields to update tunelib with changes.
        change_queue = self._read_sync_file()
        for tlop in update:
            # Just some integrity checks
            if tlop[0] != TLOP_REPLACE_FIELD:
                raise ValueError(f"Invalid operation {tlop[0]} in {tlop}")
            if tlop[2] not in (TLCOL_RATING, TLCOL_INFO, TLCOL_TITLE, TLCOL_AUTHOR, TLCOL_GENRE, TLCOL_YEAR, TLCOL_AUTOPLAY):
                raise ValueError(f"Invalid column {tlop[2]} in {tlop}")
            change_queue.append( tlop )
        self._write_sync_file( change_queue )
        # setting event would make update faster but
        # looses opportunity to process several changes in one go
        #self.sync_event.set()


    def save_lyrics( self, tuneid, new_lyrics ):
        # Save lyrics for one tune
        all_lyrics = self._read_lyrics()
        all_lyrics[tuneid] = new_lyrics
        fileops.write_json( all_lyrics, self.lyrics_filename, keep_backup=True )
        # No need for get_lyrics function since
        # javascript can get the complete lyrics.json 
        # file as data and cache int.

    def _sync_lyrics( self, newtunelib ):
        # Delete all lyrics where the tune has been deleted
        all_lyrics = self._read_lyrics()
        changes = set(all_lyrics.keys()) - set(newtunelib.keys())
        for tuneid in changes:
            del all_lyrics[tuneid]

        if changes:
            fileops.write_json( all_lyrics, self.lyrics_filename, keep_backup=True )
            self._sync_progress( "Lyrics updated" )
        
        # Mark all tunes that have lyrics
        tunelib_changes = set( tune[TLCOL_ID] for tune in newtunelib.values() if bool(tune[TLCOL_LYRICS]) != bool(tune[TLCOL_ID] in all_lyrics))
        for tuneid in tunelib_changes:
            newtunelib[tuneid][TLCOL_LYRICS] = 1 if tuneid in all_lyrics else 0
        # Caller must write tunelib.json back to flash if changed
        return bool(tunelib_changes)
    
    def add_one_to_history( self, tuneid ):
        # >>> If this queues a change instead of rewriting tunelib.json,
        # then the play/tunelist/history pages will be reloaded
        # after each tune played, which is a bit annoying.
        # But: the history count will be perfectly up to date.
        tunelib = self._read_tunelib()
        tune = tunelib.get(tuneid)
        if tune:
            tune[TLCOL_HISTORY] = tune[TLCOL_HISTORY] + 1 if tune[TLCOL_HISTORY] else 1 
            self._write_tunelib_json( tunelib )

    def _queue_change( self, tlop ):
        change_queue = self._read_sync_file()
        change_queue.append( tlop )
        self._write_sync_file(change_queue)

    # This is called to queue a file to be sync'd individually
    # (uploaded or deleted files)
    def queue_file_updated( self, path, file_size ):
        # Remember that something in the tunelib folder has changed
        # and that sync must be run
        # This is triggered by file manager and web server
        # filelist is a list of [operation, path] pairs
        self._queue_change( [ TLOP_FILE_UPDATE,
                                 fileops.get_basename(path), 
                                 file_size,0] )
        # sync process will wake up and process this file
        # Don't kick process - that way several changes are processed in one fell swoop

    def queue_file_deleted( self, path ):
        self._queue_change( [ TLOP_FILE_DELETE,
                                 fileops.get_basename(path), 
                                 0,0] )

    
    def complement_progress( self, progress ):
        progress["sync_pending"] = fileops.file_exists( self.sync_filename )
        progress["tunelib_signature"] = self.tunelib_signature
        
    def _get_initial_info( self, title ):
        try:
            p = title.lower().index("vb") - 1
            return title[p:p+4]
        except ValueError:
            return ""
     
    def _read_sync_file(self):
        return fileops.read_json(self.sync_filename, default=[])
        
    def _write_sync_file(self, change_queue):
        if len(change_queue) == 0:
            try:
                os.remove(self.sync_filename)
            except:
                pass
            return
        fileops.write_json( change_queue,  self.sync_filename, keep_backup=False )

    def file_date_dict( self ):
        # Return dictionary filename:date added for benefit of filemanager.py
        return {tune[TLCOL_FILENAME]: tune[TLCOL_DATEADDED]
                for tune in self._read_tunelib().values()}
    
    # >>> split in tunelib and tunemanager classes?