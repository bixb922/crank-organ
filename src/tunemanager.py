# (c) 2023 Hermann Paul von Borries
# MIT License
# Manages tune library.
from micropython import const
import os
import asyncio
import hashlib
import binascii
from random import random

from minilog import getLogger
import fileops
from drehorgel import timezone

# >>> print setlist with lyrics
# >>> print simple setlist (order, title, time)
# >>> print complete setlist (author, genre, year, info, rating)
# >>> browser gets tunelib.json and lyrics.json twice sometimes
# >>> detect deleted files PC vs microcontroller
# >>> Sync tunelib

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
    def __init__(self, tunelib_folder, tunelib_filename, lyrics_json, sync_tunelib_file ):
        # tunelib_folder: /tunelib, also could be /sd/tunelib
        # tunelib_filename: data/tunelib.json
        # lyrics_json: data/lyrics.json 
        # sync_tunelib_file: zero length file, if present force tunelib sync
        # This file is set when the filemanager detects upload of a MIDI file to the tunelib folder.

        self.tunelib_folder = tunelib_folder
        self.tunelib_filename = tunelib_filename
        self.lyrics_json_filename = lyrics_json
        self.sync_tunelib_filename = sync_tunelib_file
        # test if lyrics.json ok, if not, create empty
        ly = self._read_lyrics()

        self.logger = getLogger(__name__)        
        self._sync_progress( "Tunelib update not started", clear=True )
        self.sync_task = None
        # Create tunelib if no backup
        tu = self._read_tunelib()
        self.logger.debug(f"init ok, {len(tu)} tunes in {tunelib_filename}, {len(ly)} lyrics in {lyrics_json}")

        
    def _read_tunelib(self):
        return fileops.read_json(self.tunelib_filename,
                                 default={},
                                recreate=True)
    
    def _read_lyrics( self ):
        return fileops.read_json( self.lyrics_json_filename, 
                                 default={}, 
                                 recreate=True )

    def get_info_by_tuneid(self, tuneid):
        tunelib = self._read_tunelib()
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
        # Exclude rating "one star"
        # Include unrating, ** and ***
        tunelib = self._read_tunelib()
        return [
            tuneid for tuneid, v in tunelib.items() 
            if v[TLCOL_AUTOPLAY] and rating in v[TLCOL_RATING] ]

    def get_autoplay_3stars(self):
        return self.get_autoplay("***")


    def start_sync(self):
        # Called from webserver or __init__ to start synchronization
        # of tunelib folder with tunelib.json
        if self.sync_task:
            # Don't have same sync task running twice simultaneusly
            # that doesn't bode well
            return # ignore second call
        self._sync_progress( "Tunelib update not started", clear=True )
        self.sync_task = asyncio.create_task(self._sync())

    def _sync_progress( self, msg, clear=False ):
        if clear:
            self.tunelib_progress = ""
        self.tunelib_progress += msg + "<br>"
        self.logger.info( msg )

    def get_sync_progress( self ):
        # For webserver
        return self.tunelib_progress

    async def _wait_a_bit(self):
        # If sync is taking too long, yield CPU to other tasks
        # but sometimes only... not too frequently
        if random()>0.9:
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
  
    async def _check_new_changed_files( self, filedict, newtunelib ):
        changed = False
        for filename, filesize in filedict.items():
            await self._wait_a_bit()
            # Make a unique hash for this file. Hash is the
            # same for file.mid and file.mid.gz
            # Note that filename will change if there is a hash collision 
            tuneid, filename = self._make_unique_hash(filename, newtunelib)
            # Check if in tunelib and check if file has been updated
            if tuneid not in newtunelib: 
                operation = "Adding"
            elif (filesize != newtunelib[tuneid][TLCOL_SIZE] or
                  filename != newtunelib[tuneid][TLCOL_FILENAME]):
                    operation = "Updating"
            else:
                # No need to update tunelib.json for this file
                continue


            # New file detected, add to tunelib.json
            self._sync_progress( f"{operation} {filename}, computing duration" )


            # Get tune from newtunelib, if not there, create new
            tune = newtunelib.setdefault(tuneid, [""] * TLCOL_COLUMNS)
            if not tune[TLCOL_ID]:
                # New tune
                tune[TLCOL_ID] = tuneid
                # Add new tune
                # Title based on filename
                tune[TLCOL_TITLE] = ("~" + fileops.get_filename_stem(filename)).replace("-", " ").replace("_"," ").replace("  "," ")
                tune[TLCOL_AUTOPLAY] = True
            
            # Update tune if already there, but this certainly
            # also needed for new tunes
            tune[TLCOL_SIZE] = filesize
            tune[TLCOL_DATEADDED] = timezone.now_ymd()
            tune[TLCOL_TIME] = self._get_duration(filename)
            # Update filename, the file could
            # have (or not) .gz suffix
            tune[TLCOL_FILENAME] = filename

            changed = True
        return changed
    
    async def _check_deleted_files( self, filedict, newtunelib ):
        changed = False
              # Now check if files in tunelib are not in flash
        for tune in newtunelib.values():
            await self._wait_a_bit()
            # Add missing columns (this is in case
            # a new software version makes tunelib row larger)
            while len(tune) < TLCOL_COLUMNS:
                tune.append("")
            tune[TLCOL_RFU] = "" # Unused field

            # Check if MIDI file in tunelib is not in flash:
            # check with and without gz suffix
            if tune[TLCOL_FILENAME] not in filedict:
                self._sync_progress( f"{tune[TLCOL_FILENAME]} not found in flash, deleting tunelib entry" )
                # delete tunelib entry
                del newtunelib[tune[TLCOL_ID]]
                changed = True

        return changed


    async def _sync(self):
 
        # Compare tunelib.json with tunelib/*.mid
        # and update tunelib.json.
        self._sync_progress( "Starting sync", clear=True )

        changed = False

        # Don't work on current tunelib, replace
        # when finished
        tunelib = self._read_tunelib()
        # Make a shallow copy for new version
        # The new version will have more/less entries
        # The old version will be discarded
        newtunelib = dict(tunelib)

        self._sync_progress( "Listing files in tunelib folder" )

        # Yield CPU for a bit to allow webserver and other processes to run
        await asyncio.sleep_ms(20)

        # Make a dict with key=filename and data=file size (bytes)
        filedict = {inode[0]: inode[3] 
                for inode in os.ilistdir(self.tunelib_folder)
                if fileops.get_file_type( inode[0] ) == "mid"
            }
        await asyncio.sleep_ms(20)

        # Remove duplicate files (i.e. both file.mid and file.mid.gz)
        self._dedup_midi_files( filedict )
        await asyncio.sleep_ms(20)

        self._sync_progress( "Checking for new/changed files" )
        changed = changed or await self._check_new_changed_files( filedict, newtunelib )
        await asyncio.sleep_ms(20)

        self._sync_progress( "Checking for deleted files" )
        changed = changed or await self._check_deleted_files( filedict, newtunelib )
        await asyncio.sleep_ms(20)

        self._sync_progress( "Synchronizing lyrics" )
        self._sync_lyrics( newtunelib )
        await asyncio.sleep_ms(20)

        if changed:
            self._write_tunelib_json(newtunelib)
            self._sync_progress("tunelib.json written" )

        # Last element of tunelib_progress MUST contain
        # ***end*** for javascript in browser to know
        # that process has ended.
        
        self._sync_progress( "***end***" )
        self.sync_task = None


        # Sync'ing is done, delete file that may have triggered the sync
        self.forget_sync_pending()

    def _compute_hash(self, s):
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

    def _make_unique_hash(self, fn, newtunelib):
        #  .gz is not part of the hash
        # Make a collision-less hash for each file. The probability
        # of collisions is nil after a few iterations.
        for _ in range(3):
            # For historical reasons the key starts with "i"
            tuneid = "i" + self._compute_hash(fn)
            tune = newtunelib.get(tuneid, None)
            # If tune exists, and if filenames are correct, return
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

    def _write_tunelib_json(self, tunelib):
        fileops.write_json(tunelib, self.tunelib_filename, keep_backup=True)

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
            tune = tunelib[tuneid]
            index = int(tlcol_number)
            # Don't allow to change the key fields
            if index != TLCOL_FILENAME and index != TLCOL_ID and 0 <= index < TLCOL_COLUMNS:
                tune[index] = v

        self._write_tunelib_json(tunelib)
        del tunelib

    def register_comment( self, tuneid, comment ):
        tunelib = self._read_tunelib()
        tune = tunelib[tuneid]
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
            fileops.write_json( all_lyrics, self.lyrics_json_filename )


    
    def add_one_to_history( self, tuneid ):
        tunelib = self._read_tunelib()
        tune = tunelib[tuneid]
        tune[TLCOL_HISTORY] = tune[TLCOL_HISTORY] + 1 if tune[TLCOL_HISTORY] else 1 
        self._write_tunelib_json( tunelib )

    # >>> show on filemanager too?
    # >>> queue changes for sync? Store "path" in sync_tunelib_filename?
    # >>> but then each of those files must be sync'd individually, needs more code
    def remember_to_sync_tunelib( self, path ):
        # Remember that something in the tunelib folder has changed
        # and that sync must be run
        # This is not necessary for changes done in tunelibedit.html
        # since the save button on this form saves changes.
        # This is however necessary for:
        #   delete button on each row of tunelibedit.html
        #   upload of files with the filemanager to tunelib folder
        #   deleting files with the filemanager in the tunelib folder
        open( self.sync_tunelib_filename, "w").close()
        # If file exists, sync must be done

    def sync_tunelib_pending( self ):
        return fileops.file_exists( self.sync_tunelib_filename )
    
    def forget_sync_pending( self ):
        if self.sync_tunelib_pending():
            os.remove( self.sync_tunelib_filename )

    def complement_progress( self, progress ):
        progress["sync_pending"] = self.sync_tunelib_pending()
