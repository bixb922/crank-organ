# (c) 2023 Hermann Paul von Borries
# MIT License
# Manages tune library.
from micropython import const
import os
import asyncio
import hashlib
import binascii
from random import random
import time

from minilog import getLogger
import fileops
from drehorgel import timezone

# >>> print setlist with lyrics
# >>> print simple setlist (order, title, time)
# >>> print complete setlist (author, genre, year, info, rating)
# >>> browser fetches tunelib.json and lyrics.json twice sometimes


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
TLCOL_RFU = const(13)
TLCOL_COLUMNS = const(14)

class TuneManager:
    def __init__(self, tunelib_folder, tunelib_filename, lyrics_json, sync_tunelib_json ):
        # tunelib_folder: /tunelib, also could be /sd/tunelib
        # tunelib_filename: data/tunelib.json
        # lyrics_json: data/lyrics.json 
        # sync_tunelib_json: If not there: no sync pending.
        #             If it contains [], sync checks all files
        #             If it contains a non-empty list, sync check all queued files.
        # This file is set when the filemanager detects upload of a MIDI file to the tunelib folder.

        self.tunelib_folder = tunelib_folder
        self.tunelib_filename = tunelib_filename
        self.lyrics_json_filename = lyrics_json
        self.sync_tunelib_json = sync_tunelib_json
        # test if lyrics.json ok, if not, create empty
        ly = self._read_lyrics()

        self.logger = getLogger(__name__)        
        self.tunelib_progress = "Tunelib update not started"
        self.sync_task = asyncio.create_task(self._sync())
        self.sync_event = asyncio.Event()

        # Create tunelib if no backup
        tu = self._read_tunelib()
        self.logger.debug(f"init ok, {len(tu)} tunes in {tunelib_filename}, {len(ly)} lyrics in {lyrics_json}")

    def _compute_tunelib_signature( self, tunelib ):
        self.tunelib_signature = sum( tune[TLCOL_SIZE]+tune[TLCOL_TIME]  for tune in tunelib.values() )

    def _read_tunelib(self):
        tunelib = fileops.read_json(self.tunelib_filename,
                                 default={},
                                recreate=True)
        # check if some tunelib is in a very old format...
        for tuneid, tune in tunelib.items():
            if not tuneid.startswith("i") or len(tuneid) != 9:
                self.logger.info(f"Tuneid incorrect, removing tunelib entry for {tuneid} {tune[TLCOL_FILENAME]} {tune[TLCOL_TITLE]}, must sync")
                del tunelib[tuneid]
                # Must sync and populate again

        self._compute_tunelib_signature( tunelib )
        return tunelib
    
    def _write_tunelib_json(self, tunelib):
        self._compute_tunelib_signature( tunelib )
        fileops.write_json(tunelib, self.tunelib_filename, keep_backup=True)
    
    def _read_lyrics( self ):
        return fileops.read_json( self.lyrics_json_filename, 
                                 default={}, 
                                 recreate=True )

    def get_info_by_tuneid(self, tuneid):
        tunelib = self._read_tunelib()
        if tuneid not in tunelib:
            return None, 0
        filename = self.tunelib_folder + tunelib[tuneid][TLCOL_FILENAME]
        duration = tunelib[tuneid][TLCOL_TIME]
        return filename, duration

    def tune_exists( self, tuneid ):
        # All this stuff is to avoid doing file operations to check
        # if files are present when tunes are added while music plays....
        try:
            filename, _ = self.get_info_by_tuneid(tuneid)
            if filename:
                if fileops.file_exists( filename ):
                    return True
                # We'll get here if tunelibedit has not synced yet
                # and file has been deleted from the filesystem
                self.queue_tunelib_change( filename, -1 )
        except KeyError:
            # Tuneid not found in tunelib, setlist was stale, return false
            pass
        
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
        # Ask for a complete sync by setting an empty sync file
        fileops.write_json( [], self.sync_tunelib_json, keep_backup=False)
        # and kick sync task to start it
        self.sync_event.set()
        self._sync_progress("Start sync", type="start")

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
        # If both file.mid and foo.mid.gz are present,
        # erase foo.mid and keep foo.mid.gz
        # Make a copy of the set allows changing original
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
    
    def _sync_one_file( self, newtunelib, filename, filesize ):
        operation = ""
        tuneid, filename = self._make_unique_hash(filename, newtunelib)
        if filesize == -1:
            try:
                del newtunelib[tuneid]
            except KeyError:
                self.logger.info(f"File {filename} was already removed from tunelib.json")
            return "Deleting entry"
        

        # Is it a new tune or a tune update?
        tune = newtunelib.setdefault(tuneid, [""] * TLCOL_COLUMNS)
        if not tune[TLCOL_ID]: 
            operation = "Adding"
            # New tune
            tune[TLCOL_ID] = tuneid
            # Add new tune
            # Title based on filename
            tune[TLCOL_TITLE] = ("~" + fileops.get_filename_stem(filename)).replace("-", " ").replace("_"," ").replace("  "," ")
            tune[TLCOL_AUTOPLAY] = True
            tune[TLCOL_INFO] = self.get_initial_info( tune[TLCOL_TITLE] )
        # Update only if different name or different size.
        # Different name with same tuneid can happen with xxx.mid and xxx.mid.gz
        # because these two are considered equal.
        elif filesize != tune[TLCOL_SIZE] or filename != tune[TLCOL_FILENAME]:
                operation = "Updating"
        else:
            # Tune in tunelib but neither filesize nor filename changed
            return # No change

        # Update tune info both for updated and new files
        tune[TLCOL_SIZE] = filesize
        tune[TLCOL_DATEADDED] = timezone.now_ymd()
        # This can take some time!!! (up to 3 seconds per tune)
        tune[TLCOL_TIME] = self._get_duration(filename)
        # Update filename, the file could now
        # have (or not) a .gz suffix and be different from before
        tune[TLCOL_FILENAME] = filename
        return operation

    async def _sync(self):
        while True:
            # webserver may kick this but this will wake up anyhow every few
            # seconds and process what has been accumulated
            try:
                await asyncio.wait_for( self.sync_event.wait(), 10 ) # type:ignore
            except asyncio.TimeoutError:
                pass
            self.sync_event.clear()

            try:
                file_stat = os.stat(self.sync_tunelib_json)
            except OSError:
                # "no file" means: nothing pending
                continue
            # if file is young (<5 sec), wait a bit, unless file contains only
            # an empty list [], in that case sync all files right away.
            # This allows to process many files in one go (i.e. faster)
            if file_stat[6] > 2 and (time.time() - file_stat[8]) < 5:
                self.logger.debug( f"Sync file {self.sync_tunelib_json} is too young, waiting for next cycle" )
                continue  

            # By default log to flash.
            changed = False
            newtunelib = self._read_tunelib()
            change_queue = fileops.read_json(self.sync_tunelib_json, default=[])
            # Delete file right away to allow queueing more files while
            # sync is working.
            self.forget_sync_pending()

            if not change_queue:
                # Change list is there but empty, must do a complete refresh
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
                await asyncio.sleep_ms(20)

                # Queue all existing files to see if some sync'ing is needed
                change_queue = [ _ for _ in filedict.items() ]
                # and queue all files that have been deleted
                change_queue.extend( [ (tune[TLCOL_FILENAME], -1 ) 
                                    for tune in newtunelib.values() 
                                    if tune[TLCOL_FILENAME] not in filedict ] )

            for filename, filesize in change_queue:
                operation = self._sync_one_file( newtunelib, filename, filesize )
                if operation:
                    changed = True
                    self._sync_progress( f"{operation} {filename} in tunelib.json" )
                    await asyncio.sleep_ms(20)

            self._sync_lyrics( newtunelib  )
            await asyncio.sleep_ms(20)

            # Check that setlist has only valid tuneids
            from drehorgel import setlist 
            setlist.sync( newtunelib )

            if changed:
                self._write_tunelib_json(newtunelib)
                self._sync_progress("tunelib.json updated" )

            # Last element of tunelib_progress MUST contain
            # ***end*** for javascript in browser to know
            # that process has ended.
            
            self._sync_progress( "", type="end" )



    def _make_unique_hash(self, path, newtunelib):
        def _compute_hash(s):
            # Each tune has a unique hash derived from the filename
            # This is the tuneid. By design it is made unique (see _make_unique_hash)
            # and stable.
            digest = hashlib.sha256(fileops.filename_no_gz(s).encode()).digest()
            folded_digest = bytearray(6)
            i = 0
            for n in digest:
                folded_digest[i] ^= n
                i = (i + 1) % len(folded_digest)
            hash = binascii.b2a_base64(folded_digest).decode()
            # Make result compatible with URL encoding
            return hash.replace("\n", "").replace("+", "-").replace("/", "_")

        fn = path.split("/")[-1]
        #  .gz is not part of the hash
        # Make a collision-less hash for each file. The probability
        # of collisions is nil after a few iterations.
        for _ in range(3):
            # For historical reasons the key starts with "i"
            tuneid = "i" + _compute_hash(fn)
            tune = newtunelib.get(tuneid, None)
            # If new tune or if existing tune with correct filenames, return
            if not tune or fileops.filename_no_gz(tune[TLCOL_FILENAME]) == fileops.filename_no_gz(fn):
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

    def save(self, update):
        # Called from tunelibedit.html with dictionary of changed
        # fields to update tunelib with changes.
        if len(update)==0:
            return
        
        tunelib = self._read_tunelib()
        # update["tuneid.fieldname"] is a changed field coming from javascript
        # field names are translated with HEADERLIST to column numbers
        for k, v in update.items():
            tuneid, tlcol_number = k.split(".")
            tune = tunelib.get(tuneid)
            if tune:
                index = int(tlcol_number)
                # Don't allow to change the key fields and avoid index out of range
                if index != TLCOL_FILENAME and index != TLCOL_ID and 0 <= index < TLCOL_COLUMNS:
                    tune[index] = v

        self._write_tunelib_json(tunelib)
        del tunelib

    def register_comment( self, tuneid, comment ):
        tunelib = self._read_tunelib()
        tune = tunelib.get(tuneid)
        if tune:
            # Rating goes to TLCOL_RATING field
            # Info goes to TLCOL_INFO field
            if comment in ("*","**","***"):
                # Put stars in rating field
                tune[TLCOL_RATING] = comment
            else:
                tune[TLCOL_INFO] +=  "/" + comment
            self._write_tunelib_json( tunelib )
            del tunelib

    def save_lyrics( self, tuneid, new_lyrics ):
        # Save lyrics for one tune
        all_lyrics = self._read_lyrics()
        all_lyrics[tuneid] = new_lyrics
        fileops.write_json( all_lyrics, self.lyrics_json_filename, keep_backup=True )
        # No need for get_lyrics function since
        # javascript can get the complete lyrics.json 
        # file and cache it.

    def _sync_lyrics( self, newtunelib ):
        # Delete all lyrics where the tune has been deleted
        all_lyrics = self._read_lyrics()
        changes = set(all_lyrics.keys()) - set(newtunelib.keys())
        for tuneid in changes:
            del all_lyrics[tuneid]

        if changes:
            fileops.write_json( all_lyrics, self.lyrics_json_filename, keep_backup=True )
            self._sync_progress( "Lyrics updated" )

    def add_one_to_history( self, tuneid ):
        tunelib = self._read_tunelib()
        tune = tunelib.get(tuneid)
        if tune:
            tune[TLCOL_HISTORY] = tune[TLCOL_HISTORY] + 1 if tune[TLCOL_HISTORY] else 1 
            self._write_tunelib_json( tunelib )

    # This is called to queue an file to be sync'd individually
    def queue_tunelib_change( self, path, file_size ):
        # Remember that something in the tunelib folder has changed
        # and that sync must be run
        # file_size is -1 if file was deleted.
        # This is triggered by file manager and web server
        change_queue = fileops.read_json(self.sync_tunelib_json, default=[])
        # filelist is a list of [operation, path] pairs
        change_queue.append( [ fileops.get_basename(path), file_size] )
        fileops.write_json(change_queue, self.sync_tunelib_json, keep_backup=False)
        # sync process will wake up and process this file
        # Don't kick process - that way several changes are processed in one go

    def sync_tunelib_pending( self ):
        # Called to include in progress whether a sync is pending
        # This is then shown to user on top of play.html and tunelist.html
        return fileops.file_exists( self.sync_tunelib_json )
    
    def forget_sync_pending( self ):
        try:
            os.remove( self.sync_tunelib_json )
        except OSError:
            pass

    def complement_progress( self, progress ):
        progress["sync_pending"] = self.sync_tunelib_pending()
        progress["tunelib_signature"] = self.tunelib_signature

    def get_initial_info( self, title ):
        try:
            p = title.lower().index("vb") - 1
            return title[p:p+4]
        except ValueError:
            return ""
     