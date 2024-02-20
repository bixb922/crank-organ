# (c) 2023 Hermann Paul von Borries
# MIT License
# Manages tune library.

import os
import asyncio
import hashlib
import ubinascii
import umidiparser
import time


from minilog import getLogger
from config import config
from history import history
import fileops

# Define Tunelib Column names
# Must be equal to common.js
TLCOL_ID = 0
TLCOL_TITLE = 1
TLCOL_GENRE = 2
TLCOL_AUTHOR = 3
TLCOL_YEAR = 4
TLCOL_TIME = 5
TLCOL_FILENAME = 6
TLCOL_AUTOPLAY = 7
TLCOL_INFO = 8
TLCOL_DATEADDED = 9
TLCOL_RATING = 10
TLCOL_SIZE = 11
TLCOL_HISTORY = 12
TLCOL_COLUMNS = 13

# Must have names in same order as TLCOL, is used
# to decode information from web form when saving tunelib.
# These fields are defined in tunelibedit.html, function updateForm
# and function makeBox, and are part of the names of the input fields
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
]

# How to mark the title of files where the file is not on flash.
NOT_FOUND_MARK = chr(126) + "(not found) "

class TuneManager:
    def __init__(self, tunelib_folder, tunelib_json):
        self.tunelib_folder = tunelib_folder
        self.tunelib_json = tunelib_json
        self.logger = getLogger(__name__)        
        self.tunelib_progress = "Tunelib update not started"
        self.sync_task = None
        self.logger.debug(f"init ok")

        
    def read_tunelib(self):
        try:
            tunelib = fileops.read_json(self.tunelib_json)
        except OSError as e:
            self.logger.exc(e, f"tunelib {self.tunelib_json} could not be opened")
            tunelib = {}
        return tunelib
    
    def get_info_by_id(self, tuneid):
        tunelib = self.read_tunelib()
        filename = self.tunelib_folder + tunelib[tuneid][TLCOL_FILENAME]
        duration = tunelib[tuneid][TLCOL_TIME]
        del tunelib
        return filename, duration

    def get_tune_count(self):
        tunelib = self.read_tunelib()
        count = len(tunelib)
        del tunelib
        return count

    def get_autoplay(self):
        # Return list of all possible tune ids marked as autoplay.
        # used for setlist  shuffle all 
        tunelib = self.read_tunelib()
        autoplay = [
            tuneid for tuneid, v in tunelib.items() if v[TLCOL_AUTOPLAY]
        ]
        del tunelib
        return autoplay

    #def get_tunelib(self):
    #    tunelib = self.read_tunelib()
    #    # Update count of times a tune has played, and send tunelib.
    #    self._update_history_count(tunelib)
    #    return tunelib

    def _get_file_attr(self, fn):
        filename = self.tunelib_folder + fn
        osstat = os.stat(filename)
        size = osstat[6]
        cds = osstat[7]
        t = time.localtime(cds)
        creation_date = f"{t[0]}-{t[1]:02}-{t[2]:02}"
        return size, creation_date

    def start_sync(self):
        # Called from webserver to start synchronization
        # of tunelib folder with tunelib.json
        if self.sync_task:
            raise RuntimeError("Calling sync twice")
        self.tunelib_progress = "Tunelib update not started"
        self.sync_task = asyncio.create_task(self._sync())

    async def _sync(self):
        # Compare tunelib.json with tunelib/*.mid
        # and update tunelib.json.
        self.tunelib_progress = "Starting sync<br>"

        await asyncio.sleep_ms(10)
        changed = False

        # Don't disturb current tunelib, replace
        # when finished
        tunelib = self.read_tunelib()
        # Make a shallow copy for new version
        # New version will have more/less entries
        # Old version will be discarded, so changes are irrelevant
        newtunelib = dict(tunelib)

        # We will recompute which files are not found, delete mark
        for k, v in newtunelib.items():
            if v[TLCOL_TITLE].startswith(NOT_FOUND_MARK):
                v[TLCOL_TITLE] = v[TLCOL_TITLE].replace(NOT_FOUND_MARK, "")

        self.tunelib_progress += "Listing files in tunelib folder<br>"

        # Yield CPU for a bit to allow webserver and other processes to run
        await asyncio.sleep_ms(10)
        filelist = []
        for fn in os.listdir(self.tunelib_folder):
            if fn[-4:].lower() == ".mid":
                filelist.append(fn)

        self.tunelib_progress += "Checking for new files<br>"

        for fn in filelist:
            await asyncio.sleep_ms(10)

            key, fn = self._make_unique_hash(fn, newtunelib)

            filename = self.tunelib_folder + fn

            if key in tunelib:
                continue

            self.tunelib_progress += (
                f"Adding {fn}, computing duration {filename}<br>"
            )

            try:
                # Get duration in milliseconds
                duration = umidiparser.MidiFile(filename).length_us() // 1000
            except Exception as e:
                duration = 0
                self.logger.exc(e, f"Computing duration of {filename} ")

            size, creation_date = self._get_file_attr(fn)

            # [ tuneid, title=filename, genre, author. year
            #        duration, filename, autoplay, info,
            #        date added, rating, size in bytes, unused field ]
            newtunelib[key] = [
                key,
                fn[0:-4],  # filename as title
                "",
                "",
                "",
                duration,
                fn,
                True,# autoplay
                "",
                creation_date,
                "",
                size,
                0,
            ]

            changed = True

        self.tunelib_progress += "Checking for deleted files<br>"

        for k, tune in newtunelib.items():
            await asyncio.sleep_ms(10)
            # Add missing columns
            while len(tune) < TLCOL_COLUMNS:
                tune.append("")

            # Check if filename not in file list
            if tune[TLCOL_FILENAME] not in filelist:
                self.tunelib_progress += f"{tune[TLCOL_FILENAME]} in tunelib but found not in flash tunelib folder<br>"
                self.logger.info(
                    f"{tune[TLCOL_FILENAME]} not found in tunelib folder"
                )
                if not tune[TLCOL_TITLE].startswith(NOT_FOUND_MARK):
                    tune[TLCOL_TITLE] = NOT_FOUND_MARK + tune[TLCOL_TITLE]
                    tune[TLCOL_AUTOPLAY] = False
                    changed = True
            else:
                # Correct missing date added if not there
                # This is due to an old version only....
                if tune[TLCOL_DATEADDED] == "":
                    size, creation_date = self._get_file_attr(
                        tune[TLCOL_FILENAME]
                    )
                    tune[TLCOL_DATEADDED] = creation_date
                    changed = True

        await asyncio.sleep_ms(10)
        if changed:
            self.tunelib_progress += "Writing new tunelib<br>"
            await asyncio.sleep_ms(10)
            self._write_tunelib_json(newtunelib)

        # Last element of tunelib_progress MUST be
        # ***end*** for javascript in browser to know
        # that process has ended
        self.tunelib_progress += "tunelib.json written<br>"
        self.tunelib_progress += "***end***<br>"
        self.sync_task = None
        del tunelib
        del newtunelib

    def sync_progress(self):
        self.logger.debug(f"Progress {self.tunelib_progress}")
        return self.tunelib_progress

    def _compute_hash(self, s):
        # Each tune has a immutable hash derived from the filename
        # This is the tuneid. By design it is unique (see _make_unique_hash)
        # and stable.
        digest = hashlib.sha256(s.encode()).digest()
        folded_digest = bytearray(6)
        i = 0
        for n in digest:
            folded_digest[i] ^= n
            i = (i + 1) % len(folded_digest)
        hash = ubinascii.b2a_base64(folded_digest).decode()
        # Make result compatible with URL encoding
        return hash.replace("\n", "").replace("+", "-").replace("/", "_")

    def _make_unique_hash(self, fn, newtunelib):
        # Make a collision-less hash for each file

        for _ in range(3):
            key = "i" + self._compute_hash(fn)
            tune = newtunelib.get(key, None)
            if not tune or tune[TLCOL_FILENAME] == fn:
                if not tune:
                    print(f"new key {key=} {fn=} {tune=}")
                return key, fn
            print(">>>>collision", key, fn)
            # Collision. Probability is near nil: 1/2**48
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
        return key, fn

    def _write_tunelib_json(self, tunelib):
        fileops.write_json(tunelib, self.tunelib_json, keep_backup=True)

    def save(self, update):
        # Called from tunelibedit.html with dictionary of changed
        # fields to update tunelib with changes.
        if len(update)==0:
            return
        
        tunelib = self.read_tunelib()
        # update["tuneid.fieldname"] is a changed field coming from javascript
        # field names are translated with HEADERLIST to column numbers
        for k, v in update.items():
            print(f"save {k=} {v=}")

            tuneid, field = k.split(".")
            tune = tunelib[tuneid]
            if field != "clear":
                index = HEADERLIST.index(field)
                tune[index] = v
            else:
                # clear checkbox means clear info from tunelib
                if v:
                    del tunelib[tuneid]

        self._write_tunelib_json(tunelib)
        del tunelib

    def get_history(self):
        # This is used by history.html
        # Get history and add title, if available
        tunelib = self.read_tunelib()
        hist = []
        for tuneid, date, percentage, requested in history.get_events():
            tune = tunelib.get(tuneid, None)
            if tune:
                title = tune[TLCOL_TITLE]
            else:
                title = "(not found)"
            hist.append([title, date, percentage, requested])
        del tunelib
        return hist
 
                
tunemanager = TuneManager(config.TUNELIB_FOLDER, config.TUNELIB_JSON)
