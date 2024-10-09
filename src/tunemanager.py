# (c) 2023 Hermann Paul von Borries
# MIT License
# Manages tune library.
from micropython import const
import os
import asyncio
import hashlib
import binascii
import umidiparser
import time

from minilog import getLogger
from config import config
import fileops

# Define Tunelib Column names
# Must be equal to common.js
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
TLCOL_LYRICS = const(13)
TLCOL_COLUMNS = const(14)

# Must have names in same order as TLCOL, is used
# to decode information from web form when saving tunelib.
# These fields are defined in tunelibedit.html, function updateForm
# and function makeBoxField, and are part of the names of the input fields
# The changed fields are sent here for processing, see def save().
HEADERLIST = [
    "id",
    "title",
    "genre",
    "author",
    "year",
    "time",
    "filename",
    "autoplay",
    "info",
    "dateadded",
    "rating",
] # size, filename, etc are not here because they cannot be set by the user



class TuneManager:
    def __init__(self, tunelib_folder, tunelib_filename, lyrics_json, sync_tunelib_file ):
        self.tunelib_folder = tunelib_folder
        self.tunelib_filename = tunelib_filename
        self.lyrics_json = lyrics_json
        self.sync_tunelib_file = sync_tunelib_file
        if not fileops.file_exists( self.lyrics_json ):
            fileops.write_json( {}, self.lyrics_json )

        self.logger = getLogger(__name__)        
        self.tunelib_progress = "Tunelib update not started"
        self.sync_task = None
        # Create tunelib if no backup
        t = self._read_tunelib()
        self.logger.debug(f"init ok, {len(t)} tunes in {tunelib_filename}")
        if fileops.file_exists( self.sync_tunelib_file ):
            self.start_sync() 
        
    def _read_tunelib(self):
        tunelib = fileops.read_json(self.tunelib_filename,
                                    default={},
                                    recreate=True)
        return tunelib
    
    def get_info_by_id(self, tuneid):
        tunelib = self._read_tunelib()
        filename = self.tunelib_folder + tunelib[tuneid][TLCOL_FILENAME]
        duration = tunelib[tuneid][TLCOL_TIME]
        del tunelib
        return filename, duration

    def get_tune_count(self):
        tunelib = self._read_tunelib()
        count = len(tunelib)
        del tunelib
        return count

    def get_autoplay(self):
        # Return list of all possible tune ids marked as autoplay.
        # used for setlist  shuffle all 
        # Exclude rating "one star"
        # Include unrating, ** and ***
        tunelib = self._read_tunelib()
        return [
            tuneid for tuneid, v in tunelib.items() 
            if v[TLCOL_AUTOPLAY] ]

    def get_autoplay_3stars(self):
        tunelib = self._read_tunelib()
        return [
            tuneid for tuneid, v in tunelib.items() 
            if v[TLCOL_AUTOPLAY] and 
               "***" in v[TLCOL_RATING] ]

    def _get_file_attr(self, fn):
        filename = self.tunelib_folder + fn
        osstat = os.stat(filename)
        size = osstat[6]
        cds = osstat[7]
        t = time.localtime(cds)
        creation_date = f"{t[0]}-{t[1]:02}-{t[2]:02}"
        return size, creation_date

    def start_sync(self):
        # Called from webserver or __init__ to start synchronization
        # of tunelib folder with tunelib.json
        if self.sync_task:
            raise RuntimeError("Calling sync twice")
        self.tunelib_progress = "Tunelib update not started"
        self.sync_task = asyncio.create_task(self._sync())

    async def _sync(self):
        # Compare tunelib.json with tunelib/*.mid
        # and update tunelib.json.
        self.tunelib_progress = "Starting sync<br>"

        await asyncio.sleep_ms(100)
        changed = False

        # Don't work on current tunelib, replace
        # when finished
        tunelib = self._read_tunelib()
        # Make a shallow copy for new version
        # The new version will have more/less entries
        # The old version will be discarded
        newtunelib = dict(tunelib)

        self.tunelib_progress += "Listing files in tunelib folder<br>"

        # Yield CPU for a bit to allow webserver and other processes to run
        await asyncio.sleep_ms(1)
        filelist = [(inode[0], inode[3]) 
            for inode in os.ilistdir(self.tunelib_folder)
            if inode[0][-4:].lower() == ".mid"]

        self.tunelib_progress += "Checking for new files<br>"

        for fn, filesize in filelist:
            await asyncio.sleep_ms(1)
            key, fn = self._make_unique_hash(fn, newtunelib)
            # Check if in tunelib and that file hasn't been updated
            if key in tunelib and filesize == tunelib[key][TLCOL_SIZE]:
                continue
            filename = self.tunelib_folder + fn
            # New file detected, add to tunelib.json
            self.tunelib_progress += (
                f"Adding/updating {fn}, computing duration of {filename}<br>"
            )

            try:
                # Get duration in milliseconds
                duration = umidiparser.MidiFile(filename).length_us() // 1000
            except Exception as e:
                duration = 0
                self.logger.exc(e, f"Computing duration of {filename} ")

            # Get size and creation date
            size, creation_date = self._get_file_attr(fn)

            if key in newtunelib:
                # Update tune if already there
                tune = newtunelib[key]
                tune[TLCOL_SIZE] = size
                tune[TLCOL_DATEADDED] = creation_date
                tune[TLCOL_TIME] = duration
            else:
                # Add new tune
                # [ tuneid, title=based on filename, genre, author. year
                #        duration, filename, autoplay, info,
                #        date added, rating, size in bytes, unused field ]
                initial_title = ("~" + fn[0:-4]).replace("-", " ").replace("_"," ").replace("  "," ")
                newtunelib[key] = [
                    key,
                    initial_title, 
                    "",
                    "",
                    "",
                    duration, # Will be recomputed if size changes
                    fn,
                    True, # autoplay by default
                    "",
                    creation_date, # Will not be updated
                    "",
                    size, # Will be checked on each sync
                    0,
                ]

            changed = True

        self.tunelib_progress += "Checking for deleted files<br>"

        # Make a dict for filelist for faster query
        filedict = dict( ( fn, 0 ) for fn, _ in filelist )
        for  tune in newtunelib.values():
            await asyncio.sleep_ms(1)
            # Add missing columns
            while len(tune) < TLCOL_COLUMNS:
                tune.append("")

            # Check if file in tunelib is not in flash:
            if tune[TLCOL_FILENAME] not in filedict:
                self.tunelib_progress += f"{tune[TLCOL_FILENAME]} in tunelib but found not in flash tunelib folder, deleting entry<br>"
                self.logger.info(
                    f"{tune[TLCOL_FILENAME]} not found in tunelib folder"
                )
                # delete tunelib entry
                del newtunelib[tune[TLCOL_ID]]
                changed = True

        await asyncio.sleep_ms(10)
        self.tunelib_progress += "Synchronizing lyrics<br>"
        changed = changed or self._sync_lyrics( newtunelib )

        if changed:
            self.tunelib_progress += "Writing new tunelib<br>"
            await asyncio.sleep_ms(10)
            self._write_tunelib_json(newtunelib)
            self.tunelib_progress += "tunelib.json written<br>"

        # Last element of tunelib_progress MUST contain
        # ***end*** for javascript in browser to know
        # that process has ended
        
        self.tunelib_progress += "***end***<br>"
        self.sync_task = None
        del tunelib
        del filelist
        del filedict
        del newtunelib

        # Sync'ing is done, delete file that may have triggered the sync
        if fileops.file_exists( self.sync_tunelib_file ):
            os.remove( self.sync_tunelib_file )

    def sync_progress(self):
        self.logger.debug(f"Progress {self.tunelib_progress}")
        return self.tunelib_progress
    
    def _compute_hash(self, s):
        # Each tune has a unique hash derived from the filename
        # This is the tuneid. By design it is made unique (see _make_unique_hash)
        # and stable.
        digest = hashlib.sha256(s.encode()).digest()
        folded_digest = bytearray(6)
        i = 0
        for n in digest:
            folded_digest[i] ^= n
            i = (i + 1) % len(folded_digest)
        hash = binascii.b2a_base64(folded_digest).decode()
        # Make result compatible with URL encoding
        return hash.replace("\n", "").replace("+", "-").replace("/", "_")

    def _make_unique_hash(self, fn, newtunelib):
        # Make a collision-less hash for each file. The probability
        # of collisions is nil after a few iterations.
        for _ in range(3):
            # For historical reasons the key starts with "i"
            key = "i" + self._compute_hash(fn)
            tune = newtunelib.get(key, None)
            if not tune or tune[TLCOL_FILENAME] == fn:
                return key, fn
            
            self.logger.error("Key collision, please rename this tune:", key, fn)
            # Collision. Probability is near nil, of the 
            # order of 1/2**48
            # Change filename to get another hash
            newfn = fn.replace(".", "_.")
            self.logger.info(
                f"Hash collision, rename {fn} to {newfn}, lucky day"
            )
            # Change filename to avoid hash collisions...
            filename = self.tunelib_folder + fn
            newfilename = self.tunelib_folder + newfn
            os.rename(filename, newfilename)
            fn = newfn
            # Now hash function should be one-to-one, no collisions
        return key, fn

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

            tuneid, field = k.split(".")
            tune = tunelib[tuneid]
            index = HEADERLIST.index(field)
            # Don't allow to change key fields
            if index != TLCOL_FILENAME and index != TLCOL_ID and index < TLCOL_COLUMNS:
                tune[index] = v

        self._write_tunelib_json(tunelib)
        del tunelib

    def register_comment( self, tuneid, comment ):
        tunelib = self._read_tunelib()
        tune = tunelib[tuneid]
        if comment in ("*","**","***"):
            # Put stars in rating field
            tune[TLCOL_RATING] = comment
        else:
            # Put tet in info field
            tune_info = tune[TLCOL_INFO].strip()
            if len(tune_info)>0:
                if tune_info[-1] != ".":
                    tune_info += ". "
            tune[TLCOL_INFO] = tune_info + comment
        self._write_tunelib_json( tunelib )
        del tunelib

    def save_lyrics( self, tuneid, new_lyrics ):
        all_lyrics = fileops.read_json( self.lyrics_json,
                                        default=[],
                                        recreate=True )
        all_lyrics[tuneid] = new_lyrics
        fileops.write_json( all_lyrics, self.lyrics_json, keep_backup=True )
        # No need for get_lyrics function since
        # javascript can get the complete lyrics.json 
        # file and cache it.

    def _sync_lyrics( self, newtunelib ):
        # Delete all lyrics where the tune has been deleted
        all_lyrics = fileops.read_json( self.lyrics_json,
                                        default=[],
                                        recreate=True )
        changed = False
        for tuneid in all_lyrics.keys():
            if tuneid not in newtunelib:
                del all_lyrics[tuneid]
                changed = True

        # Set the "lyrics" indicator
        tunelib_changed = False
        for tuneid, tune in newtunelib.items():
            t = tuneid in all_lyrics
            if tune[TLCOL_LYRICS] != t:
                tune[TLCOL_LYRICS] = t
                tunelib_changed = True

        if changed:
            fileops.write_json( all_lyrics, self.lyrics_json )

        return tunelib_changed
    
    def add_one_to_history( self, tuneid ):
        tunelib = self._read_tunelib()
        tune = tunelib[tuneid]
        if not tune[TLCOL_HISTORY]:
            tune[TLCOL_HISTORY] = 1
        else:
            tune[TLCOL_HISTORY] += 1
        self._write_tunelib_json( tunelib )

    def remember_to_sync_tunelib( self ):
        # Remember that something in the tunelib folder has changed
        # and that sync must be run
        # This is not necessary for changes done in tunelibedit.html
        # since the save button on this form saves changes.
        # This is however necessary for:
        #   delete button on each row of tunelibedit.html
        #   upload of files with the filemanager to tunelib folder
        #   deleting files with the filemanager in the tunelib folder
        open( self.sync_tunelib_file, "w").close()
        # If file exists, sync must be done

tunemanager = TuneManager(config.TUNELIB_FOLDER, config.TUNELIB_JSON, config.LYRICS_JSON, config.SYNC_TUNELIB )
