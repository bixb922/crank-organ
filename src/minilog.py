# (c) 2023 Hermann Paul von Borries
# MIT License
# Records event log. Limits total event log size, so event logs can't
# hog flash memory.
# Default mode is: debug messages to console, info messages to flash.
from micropython import const
import sys
import io
import os
import re

from scheduler import singleton
from drehorgel import timezone

# DEBUG: only to console, rather fast
# INFO, ERROR, EXCEPTION: to flash. Can be rather slow but is immediately persistent 
DEBUG = const(0) 
INFO = const(1)
ERROR = const(2)
EXCEPTION = const(3)
_LEVELNAMES = ["DEBUG", "INFO", "ERROR", "EXCEPTION"]

_FOLDER = "data/"  # Do not define in config, minilog should be autonomous.

# BaseLogger class is internal to minilog, does the work.
# The call interface is with function getLogger and class Logger

_FILE_LEVEL = INFO
# Normal playing = about 120 bytes of log usage.
# 1 logfile = about 160 tunes = 8 hours of playing at 20 tunes/hr
# Limiting number of log files and size of logfiles ensures
# that logfiles never fill flash completely, even with a
# runaway error
_KEEP_FILES = const(4)
_MAX_LOGFILE_SIZE = const(20_000)

@singleton
class BaseLogger:
    def __init__(self):
        # Count of event logs since reboot
        self.error_count = 0
        # Compute new filename for error.log
        # Find error<nnn>.log file with highest nnn
        self.max_num = max((n for n, _ in self._filenumbers()),default=0)
        self.current_log_filename = self._makefilename(self.max_num)
        self.file = open(self.current_log_filename, "a")
        # logging an entry takes 150 msec, rest of __init__ is <15msec
        # But it is important to log a RESTART to flash.
        self.log(__name__, INFO, "=== RESTART ===")

    def _check_max_logfile_size(self):
        # If maximum filesize exceeded, use new file name
        if self.file.tell() < _MAX_LOGFILE_SIZE:
            return
        self.file.close()
        self.max_num += 1
        self.current_log_filename = self._makefilename(self.max_num)
        self.file = open(self.current_log_filename, "w")
        self.log(
            __name__, DEBUG, f"now logging to {self.current_log_filename}"
        )

        # Delete oldest
        for n, filename in self._filenumbers():
            if (self.max_num - n) >= _KEEP_FILES:
                os.remove(filename)
                self.log(__name__, INFO, f"old log {filename} deleted")

    def _makefilename(self, n):
        return f"{_FOLDER}error{n}.log"

    def _filenumbers(self):
        # List numbers of error logs, example:
        # error10.log, error11.log, error12.log
        # will yield 10, 11, 12 as integers
        pattern = re.compile("^error([0-9]+)\\.log$")
        filenumber = None
        for filename in os.listdir(_FOLDER):
            match = re.match(pattern, filename)
            if not match:
                # This is not a error*.log file
                continue
            # group(0): entire string, group 1: number error<nnn>.log
            try:
                filenumber = int(match.group(1))
            except ValueError:
                # Not a number, skip this file
                continue
            yield filenumber, _FOLDER + filename
        if filenumber is None:
            # No error*.log file yet
            yield 0, self._makefilename(0)

    def _formatRecord(self, module, level, message):
        now = timezone.now_ymdhmsz()
        return f"{now} - {module} - {_LEVELNAMES[level]} - {message}"

    def _write(self, s):
        self.file.write(s)
        self.file.flush()
        self._check_max_logfile_size()

    def log(self, module, level, message):
        s = self._formatRecord(module, level, message)
        print(s)
        if level >= _FILE_LEVEL:
            self._write(f"{s}\n")

        if level == ERROR:
            self.error_count += 1

    def exception(self, module, message, exception):
        # Count exceptions as errors
        self.error_count += 1

        s = self._formatRecord(module, EXCEPTION, message)
        # Format exception to a string
        with io.BytesIO() as bytefile:
            sys.print_exception(exception, bytefile)
            exception_text = bytefile.getvalue().decode() # type: ignore
            exception_text = "       " + exception_text.replace("\n", "\n       ")
        # Output exception to console and file
        print(s)
        print(exception_text)
        self._write(f"{s}\n{exception_text}\n")

    def get_current_log_filename(self):
        return self.current_log_filename

    def get_error_count(self):
        return self.error_count

# To start a logger in a module use
# import minilog
# logger = minilog.getLogger( __name __ )
# logger.debug("debug message")
# logger.info("informational message")
# logger.exc( exception, "exception message")
class getLogger:
    # This class is the public interface to minilog
    # Instead of making BaseLogger a singleton,
    # we pass it as a optional keyword argument to getLogger
    # to ensure it is only created once.
    def __init__(self, module, baselogger=BaseLogger() ):
        self.module = module
        self.baselogger = baselogger

    def debug(self, message):
        self.baselogger.log(self.module, DEBUG, message)

    def info(self, message):
        self.baselogger.log(self.module, INFO, message)

    def error(self, message):
        self.baselogger.log(self.module, ERROR, message)

    def exc(self, exception, message):
        self.baselogger.exception(self.module, message, exception)

    def get_current_log_filename(self):
        return self.baselogger.get_current_log_filename()

    def get_error_count(self):
        return self.baselogger.get_error_count()
