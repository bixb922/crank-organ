import json
import os
import gc

from minilog import getLogger
import config

def _init():
    global _logger, _autoplay, _tunedict
    _logger = getLogger( __name__ )
    # Get list of autoplay tuneids and translation from tuneid to
    # filename. The rest of the information in the tuneids.json
    # is for the web pages, to be used by javascript.
    try:
        with open( config.MUSIC_JSON ) as file:
            tunes = json.load( file )
    except OSError as e:
        _logger.exc(e, f"tunelib {config.MUSIC_JSON} could not be opened")
        tunes = { "header": ["id", "filename", "autoplay"],
                  "autoplay": []
                }
    _autoplay = tunes["autoplay"]
    # Build _tunedict = translates tune id to file name.
    nameindex = tunes["header"].index("filename")
    idindex = tunes["header"].index("id")
    # keys starting with "i" are tunes, contents is a list
    # described by "header" entry.
    _tunedict = dict( (( tune[idindex], tune[nameindex] )
            for k, tune in tunes.items()
            if k[0:1] == "i" ) )
    _logger.debug(f"init ok {len(_tunedict)} tunes")
         
            
def get_filename_by_number( tuneid ):
    return config.MUSIC_FOLDER + _tunedict[tuneid]

def get_tune_count():
    return len( _tunedict )

def get_autoplay():
    # Return list of all possible tune ids marked as autoplay.
    return _autoplay

_init()
