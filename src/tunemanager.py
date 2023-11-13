# (c) 2023 Hermann Paul von Borries
# MIT License
# Manages tune library.

import json
import os
import asyncio
import hashlib
import ubinascii
import umidiparser
import time
from collections import OrderedDict

import scheduler
from minilog import getLogger
from config import config
from history import history
import fileops

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
HEADERLIST = [ "id", "title", "genre", "author", "year", "time", "filename", "autoplay", "info", "dateadded", "rating"]

NOT_FOUND_MARK = chr(126)+"(not found) "

class TuneManager:
    def __init__( self, music_folder, music_json  ):
        self.music_folder = music_folder
        self.music_json = music_json 
        self.logger = getLogger( __name__ )
        
        # Get list of autoplay tuneids and translation from tuneid to
        # filename. The rest of the information in the tuneids.json
        # is for the web pages, to be used by javascript.
        
        try:
            self.tunelib = fileops.read_json(  self.music_json )
        except OSError as e:
            self.logger.exc(e, f"tunelib {self.music_json} could not be opened")
            self.tunelib = {  }
        
        self.update_history_task = asyncio.create_task(
                    self._update_history_process() )
        self.tunelib_progress = "Tunelib update not started"
        self.sync_task = None
        self.logger.debug(f"init ok {len(self.tunelib)} tunes")
 
    def get_filename_by_id( self, tuneid ):
        return self.music_folder + self.tunelib[tuneid][TLCOL_FILENAME]

    def get_tune_count( self ):
        return len( self.tunelib )

    def get_autoplay( self ):
        # Return list of all possible tune ids marked as autoplay.
        return [ v[TLCOL_ID] 
                         for k, v in self.tunelib.items() 
                         if v[TLCOL_AUTOPLAY] ]

    def get_tunelib( self ):
        return self.tunelib

    def start_sync( self ):
        if self.sync_task:
            raise RuntimeError("Calling sync twice")
        self.tunelib_progress = "Tunelib update not started"
        self.sync_task = asyncio.create_task( self._sync() )

    def _get_file_attr( self, fn ):
        filename = self.music_folder + fn
        osstat = os.stat( filename )
        size = osstat[6]
        cds = osstat[7]
        t = time.localtime( cds )
        creation_date = f"{t[0]}-{t[1]:02}-{t[2]:02}"
        return size, creation_date

    async def _sync( self ):
        # Make a backup per day


        # Compare tunelib.json with tunelib/*.mid
        # and update tunelib.

        self.tunelib_progress = "Starting sync"

        await asyncio.sleep_ms(10)
        changed = False

        # Don't disturb current tunelib
        newtunelib = dict( self.tunelib )

        # We will recompute which files are not found, delete mark
        for k,v in newtunelib.items():
            if v[TLCOL_TITLE].startswith(NOT_FOUND_MARK):
                v[TLCOL_TITLE] = v[TLCOL_TITLE].replace( NOT_FOUND_MARK, "" )

        self.tunelib_progress = "Listing files in tunelib folder"

        await asyncio.sleep_ms(10)
        filelist = []
        for fn in os.listdir( self.music_folder ):
            if fn.endswith(".MID") or fn.endswith(".mid"):
                filelist.append( fn ) 

        self.tunelib_progress = "Checking for new files"

        for fn in filelist:
            await asyncio.sleep_ms(10)

            key, fn = self._make_unique_hash( fn, newtunelib )

            filename = self.music_folder + fn    

            if key in self.tunelib:
                continue

            self.tunelib_progress = f"Adding {fn}, computing duration {filename}"

            try:
                # Get duration in milliseconds
                duration = umidiparser.MidiFile( filename).length_us()//1000
            except Exception as e:
                duration = 0
                self.logger.exc( e, f"Computing duration of {filename} ")

            size, creation_date = self._get_file_attr( fn )

            #[ tuneid, title=filename, genre, author. year
            #        duration, filename, autoplay, info, date added, rating, size in bytes, unused field ]
            newtunelib[key] = [ key, fn[0:-4], "", "", "", 
                             duration, fn, True, "", creation_date, "", size, 0  ]

            changed = True   

        self.tunelib_progress = "Checking for deleted files"

        for k, tune in newtunelib.items():
            await asyncio.sleep_ms(10)
            # Add missing columns
            while len( tune ) < TLCOL_COLUMNS:
                tune.append( "" )

            # Check if filename not in file list
            if tune[TLCOL_FILENAME] not in filelist:
                self.logger.info(f"{tune[TLCOL_FILENAME]} not found in tunelib folder")
                if not tune[TLCOL_TITLE].startswith( NOT_FOUND_MARK):
                    tune[TLCOL_TITLE] = NOT_FOUND_MARK + tune[TLCOL_TITLE]
                    tune[TLCOL_AUTOPLAY] = False
                    changed = True
            else:
                if tune[TLCOL_DATEADDED] == "":
                    size, creation_date = self._get_file_attr( tune[TLCOL_FILENAME] )
                    tune[TLCOL_DATEADDED] = creation_date
                    changed = True

        await asyncio.sleep_ms(10) 
        if changed:
            self.tunelib_progress = "Writing new tunelib"
            await asyncio.sleep_ms(10)
            self.tunelib = newtunelib
            self._write_tunelib_json( )

        self.tunelib_progress = ""
        self.sync_task = None

    def sync_progress( self ):
        self.logger.debug(f"Progress {self.tunelib_progress}")
        return self.tunelib_progress

    def _compute_hash( self, s ):
        digest = hashlib.sha256( s.encode() ).digest()
        folded_digest = bytearray(6)
        i = 0
        for n in digest:
            folded_digest[i] ^= n
            i = (i + 1)%len(folded_digest)
        hash = ubinascii.b2a_base64( folded_digest ).decode()
        # Make result compatible with URL encoding
        return hash.replace("\n", "").replace("+", "-").replace("/","_")

    def _make_unique_hash( self, fn, newtunelib ):
        # Make a collision-less hash for each file

        for _ in range(3):
            key = "i" + self._compute_hash( fn )
            tune = newtunelib.get(key, None)
            if not tune or tune[TLCOL_FILENAME] == fn:
                if not tune:
                    print(f"new key {key=} {fn=} {tune=}")
                return key, fn
            print(">>>>collision", key, fn)
            # Collision. Probability is near nil: 1/2**48
            # Change filename to get another hash
            newfn = fn.replace(".", "_.")
            self.logger.info(f"Hash collision, rename {fn} to {newfn}, lucky day")
            filename = self.music_folder + fn
            newfilename = self.music_folder + newfn
            os.rename( filename, newfilename )
            fn = newfn
        return key, fn

    def _write_tunelib_json( self ):
        fileops.write_json( self.tunelib, self.music_json )
    

    def save( self, update ):
        # update[hash.fieldname] is a changed field
        for k,v in update.items():
            print(f"save {k=} {v=}")

            tuneid, field = k.split(".")
            tune = self.tunelib[tuneid]
            if field != "clear":
                index = HEADERLIST.index( field )
                tune[index] = v
            else:
                # clear checkbox means clear info from tunelib
                if v:
                    del self.tunelib[tuneid]

        self._write_tunelib_json(  )

    def get_duration( self, tuneid ):
        return self.tunelib[tuneid][TLCOL_TIME]

    def get_history( self ):
        # Get history and add title, if available
        hist = []
        for tuneid, date, percentage in history.get_all_events():
            tune = self.tunelib.get(tuneid, None)
            if tune:
                title = tune[TLCOL_TITLE]
            else:
                title = "(not found)"
            hist.append( [title, date, percentage] )
        return hist

    async def _update_history_process( self ):
        # Update the history info once every startup
        async with scheduler.RequestSlice( "history", 2000 ):
            for tuneid, tune in self.tunelib.items():
                tune[TLCOL_HISTORY] = 0
            for tuneid, date, percentage in  history.get_all_events():
                    tune = self.tunelib.get( tuneid, None )
                    if tune:
                        tune[TLCOL_HISTORY] += 1
            self._write_tunelib_json( keep_backup=False )
        self.logger.debug("Tunelist history updated")

  
tunemanager = TuneManager( 
    config.MUSIC_FOLDER, 
    config.MUSIC_JSON )


