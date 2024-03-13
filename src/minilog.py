# (c) 2023 Hermann Paul von Borries
# MIT License
# Records event log. Limits total event log size, so event logs can't
# hog flash memory.
# Default mode is: debug messages to console, info messages to flash.
import sys
import io
import os
import re

from timezone import timezone

DEBUG = const(0)  # Goes only to console to make it light on CPU usage
INFO = const(1)
ERROR = const(2)
EXCEPTION = const(3)
_LEVELNAMES = ["DEBUG", "INFO", "ERROR", "EXCEPTION"]

_FOLDER = "data/"  # Do not define in config, minilog should be autonomous.

# BaseLogger class is internal to minilog, does the work.
# The call interface is with function getLogger and class Logger

_FILE_LEVEL = INFO
_LOG_MEMORY = const(False)
_KEEP_FILES = const(4)
_MAX_LOGFILE_SIZE = const(20_000)


class BaseLogger:
    def __init__(self):
        # Count of event logs since reboot
        self.error_count = 0
        # Compute new filename for error.log
        # Find error<nnn>.log file with highest nnn
        self.max_num = max(n for n, _ in self._filenumbers())
        self.current_log_filename = self._makefilename(self.max_num)
        self.file = open(self.current_log_filename, "a")
        # logging an entry takes 150 msec, rest of __init__ is <15msec
        self._log(__name__, INFO, "=== RESTART ===")

    def _check_max_logfile_size(self):
        # If maximum filesize exceeded, use new file name
        if self.file.tell() < _MAX_LOGFILE_SIZE:
            return
        self.file.close()
        self.max_num += 1
        self.current_log_filename = self._makefilename(self.max_num)
        self.file = open(self.current_log_filename, "w")
        self._log(
            __name__, DEBUG, f"now logging to {self.current_log_filename}"
        )

        # Delete oldest
        for n, filename in self._filenumbers():
            if (self.max_num - n) >= _KEEP_FILES:
                os.remove(filename)
                self._log(__name__, INFO, f"old log {filename} deleted")

    def _makefilename(self, n):
        return f"{_FOLDER}error{n}.log"

    def _filenumbers(self):
        # List numbers of error logs, example:
        # error10.log, error11.log, error12.log
        # will yield 10, 11, 12 as integers
        pattern = re.compile("^error([0-9]+)\.log$")
        filenumber = None
        for filename in os.listdir(_FOLDER):
            if not (match := re.match(pattern, filename)):
                continue
            # group(0): entire string, group 1: number
            filenumber = int(match.group(1))
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

    def _log(self, module, level, message):
        s = self._formatRecord(module, level, message)
        print(s)
        if level >= _FILE_LEVEL:
            self._write(f"{s}\n")

        if level == ERROR:
            self.error_count += 1

    def _exception(self, module, message, exception):
        # Count exceptions as errors
        self.error_count += 1

        s = self._formatRecord(module, EXCEPTION, message)
        # Format exception to a string
        bytefile = io.BytesIO()
        sys.print_exception(exception, bytefile)
        exception_text = bytefile.getvalue().decode()
        exception_text = "       " + exception_text.replace("\n", "\n       ")
        # Output exception to console and file
        print(s)
        print(exception_text)
        self._write(f"{s}\n{exception_text}\n")

    def _get_current_log_filename(self):
        return self.current_log_filename

    def _get_error_count(self):
        return self.error_count


class Logger:
    # This class is the public interface to minilog
    def __init__(self, module, baselogger):
        self.module = module
        self.baselogger = baselogger

    def debug(self, message):
        self.baselogger._log(self.module, DEBUG, message)

    def info(self, message):
        self.baselogger._log(self.module, INFO, message)

    def error(self, message):
        self.baselogger._log(self.module, ERROR, message)

    def exc(self, exception, message):
        self.baselogger._exception(self.module, message, exception)

    def get_current_log_filename(self):
        return self.baselogger._get_current_log_filename()

    def get_error_count(self):
        return self.baselogger._get_error_count()


_baselogger = BaseLogger()


# To start a logger in a module use
# from minilog import getLogger
# logger = getLogger( __name __ )
def getLogger(module):
    logger = Logger(module, _baselogger)
    #>>>logger.debug("getLogger")
    return logger
