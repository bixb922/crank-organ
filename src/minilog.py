# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

# Records event log. Limits total and individual event log size, so event logs can't
# hog flash memory.

# Usage:
#   import minilog
#   logger = minilog.getLogger( __name __ )
#   logger.debug("debug message")
#   logger.info("informational message")
#   logger.exc( exception, "exception message")
    
# Default mode is: debug messages to console, info messages to flash.
from micropython import const
import sys
import io
import os
import re
from time import localtime

from compiledate import compiledate 

# DEBUG: only to console, fast
# INFO, ERROR, EXCEPTION: to flash. Can be rather slow but is always persistent 
_LEVELNAMES = ["DEBUG", "INFO", "ERROR", "EXCEPTION"]

_FOLDER = const("data/")  # Do not use config, minilog should be autonomous.


# Normal music playing = about 500-1000 bytes of log usage.
# 1 logfile of 20k = about 40 tunes = 4 hours of playing at a normal rate
# 2 log files cover about 1 day of intense activity.
# Limiting number of log files and size of logfiles ensures
# that logfiles never fill flash completely, even with a
# runaway error
_KEEP_FILES = const(4)
_MAX_LOGFILE_SIZE = const(20_000)

    
class getLogger:
    _file_level = "INFO"
    _error_count = 0 # Count of event logs since reboot
    _current_log_num = 0 # from 1 up. 0 means "class not initialized"
    # Other class variables:
    #   _file    handle of current error.log file
    #   _timezone

    @classmethod
    def set_file_level( cls, log_debug ):
        # Can only set DEBUG or INFO levels.
        cls._file_level = "DEBUG" if log_debug else "INFO"

    @classmethod
    def set_timezone( cls, timezone ):
        # timezone must be injected before the first log entry 
        # is written.
        cls._timezone = timezone

    @classmethod
    def _class_init(cls):
        if cls._current_log_num:
            # already initialized
            return
        
        # Compute new filename for error.log
        # Find error<nnn>.log file with highest nnn
        cls._current_log_num = max((n for n in cls._filenumbers()),default=1)
        cls._file = open(cls._makefilename(cls._current_log_num), "a")
        # logging an entry can take 150 msec, rest of __init__ is <15msec
        # But it is important to log the RESTART to flash.
        cls.log(__name__, "INFO", f"=== RESTART version {compiledate} ===")


        # Delete oldest log file
        for n in cls._filenumbers():
            if (cls._current_log_num - n) >= _KEEP_FILES:
                filename = cls._makefilename(n)
                os.remove(filename)
                cls.log(__name__, "INFO", f"old log {filename} deleted")

    @classmethod
    def _makefilename(cls, n):
        return f"{_FOLDER}error{n}.log"

    @classmethod
    def _filenumbers(cls):
        # List numbers of error logs, example:
        # error10.log, error11.log, error12.log
        # will yield 10, 11, 12 as integers
        pattern = re.compile("^error([0-9]+)\\.log$")
        notfound = True  # to detect if a file number was found
        for filename in os.listdir(_FOLDER):
            match = re.match(pattern, filename)
            if match:
                # group(0): entire string, group(1): number nnn of error<nnn>.log
                try:
                    notfound = False
                    yield int(match.group(1))
                except ValueError:
                    # Not a number, skip this file
                    continue
        # No error*.log file yet, initalize 
        if notfound:
            yield 1
        # Return None to stop iteration

    @classmethod
    def _formatRecord(cls, module, level, message):
        try:
            tz = cls._timezone.now_ymdhmsz()
        except:
            # Should not happen.
            tz = "??:??:??"
        return f"{tz} - {module} - {level} - {message}"
        
    @classmethod
    def _write(cls, s):
        cls._file.write(s)
        cls._file.flush()
        if cls._file.tell() < _MAX_LOGFILE_SIZE:
            return
        # If maximum filesize exceeded with this write, switch to new file
        cls._file.close()
        cls._current_log_num += 1
        filename = cls._makefilename(cls._current_log_num)
        cls._file = open(filename, "w")
        cls.log( __name__, "DEBUG", f"now logging to log file {filename}" )


    @classmethod
    def log(cls, module, level, message):
        s = cls._formatRecord(module, level, message)
        print(s)
        if _LEVELNAMES.index(level) >= _LEVELNAMES.index(cls._file_level):
            cls._write(f"{s}\n")

        if level == "ERROR" or level == "EXCEPTION":
            cls._error_count += 1

    @classmethod
    def _exception(cls, module, message, exception):
        # Count exceptions as errors
        cls._error_count += 1

        s = cls._formatRecord(module, "EXCEPTION", message)
        # Format exception to a string
        with io.BytesIO() as bytefile:
            sys.print_exception(exception, bytefile)
            exception_text = bytefile.getvalue().decode() # type: ignore
            exception_text = "       " + exception_text.replace("\n", "\n       ")
        # Output exception to console and file
        print(s)
        print(exception_text)
        cls._write(f"{s}\n{exception_text}\n")

    # ============================
    # Instance methods
    def __init__(self, module ):
        # initialize class, if not already initalized.
        getLogger._class_init()
        self.module = module

    # For all methods here, call corresponding class method.
    def get_current_log_filename(self):
        return self._makefilename( self._current_log_num )

    def get_error_count(self):
        return self._error_count

    def debug(self, message):
        self.log(self.module, "DEBUG", message)

    def info(self, message):
        self.log(self.module, "INFO", message)

    def error(self, message):
        self.log(self.module, "ERROR", message)

    def exc(self, exception, message):
        self._exception(self.module, message, exception)
