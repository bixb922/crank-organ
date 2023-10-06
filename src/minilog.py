# Records event log. Limits total event log size, so event logs can't
# hog flash memory.
# Default mode is: debug messages to console, info messages to flash.
import gc
import sys
import io
import time
import os
import json

        
DEBUG = const(0) # Goes only to console to make it light on CPU usage
INFO = const(1)
ERROR = const(2)
EXCEPTION = const(3)
_LEVELNAMES = ["DEBUG", "INFO", "ERROR", "EXCEPTION" ]

_FOLDER = "data" # Do not define in config, minilog has to be autonomous.
_PREFIX = "error"
_FTYPE = ".log"

# Namespace for global variables
class _NameSpace:
    pass
_glb = _NameSpace()

# This class is internal to minilog, does the work.
# The call interface is with function getLogger and class Logger
# Except to set parameters, use for example:
# BaseLogger( max_glb.current_logfile_size=10_000, fileLevel=minilog.ERROR )

_FILE_LEVEL = INFO
_LOG_MEMORY = const(False)
_KEEP_FILES = const(4)
_MAX_LOGFILE_SIZE = const(20_000)

def _init( ):
    _glb.tzoffset = 0
    
    # Count of event logs since reboot
    _glb.error_count = 0 
    # Compute new filename for error.log
    # Find error<nnn>.log file with highest nnn (last event log)
    _glb.max_num = -1
    for n, filename in _filenumbers():
        _glb.max_num = max( n, _glb.max_num )
    _glb.current_log_filename = _makefilename( _glb.max_num )

    # Get size of this log file
    try:
        _glb.current_logfile_size = os.stat(_glb.current_log_filename)[6]
    except:
        _glb.current_logfile_size = 0

    _log( __name__, INFO, "=== RESTART ===" )
    
        
def _check_max_logfile_size( ):    
    # If maximum filesize exceeded, use new file name
    if _glb.current_logfile_size > _MAX_LOGFILE_SIZE:  
        _glb.max_num += 1
        _glb.current_log_filename = _makefilename( _glb.max_num )
        _glb.current_logfile_size = 0
        _log( __name__, DEBUG, f"logging to {_glb.current_log_filename}" )
        
        # Delete oldest
        for n, filename in _filenumbers():
                if _glb.max_num - n >= _KEEP_FILES:
                    os.remove( filename )
                    _log( __name__, INFO, f"old log {filename} deleted" )
                    
def _makefilename( n ):
    return f"{_FOLDER}/{_PREFIX}{n}{_FTYPE}"

def _filenumbers( ):
    p = len(_PREFIX)
    q = len(_FTYPE)
    filenumber = None
    # List numbers of error_10_*.log, error_11_*.log, error_12_*.log files
    for filename in os.listdir( _FOLDER ):
        # Only look at files of the form error*.log
        if filename[0:p] == _PREFIX and filename[-q:] == _FTYPE :
            try:
                filenumber = int(filename[p:-q])
            except:
                filenumber = 0
            yield filenumber, _FOLDER + "/" + filename
    if filenumber is None:
        # No error*.log file yet
        yield 0, _makefilename( 0 )

def _formatTime():
    if _glb.tzoffset <= 24:
        t = time.localtime( time.time() + _glb.tzoffset )
    else:
        t = ttz.now()
    if t[0] < 2010:
        # No ntptime yet
        return f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
    else:
        return f"{t[0]}/{t[1]:02d}/{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
        
def _formatRecord( module, level, message ):
    return f"{_formatTime()} - {module} - {_LEVELNAMES[level]} - {message}"

def _log( module, level, message ):

    s = _formatRecord( module, level, message )
    print( s )
    if level >= _FILE_LEVEL:
        with open( _glb.current_log_filename, "a") as file:
            file.write( s )
            file.write( "\n" )
            _glb.current_logfile_size += len(s) + 1
        _check_max_logfile_size()

    if level == ERROR:
        _glb.error_count += 1
        import led
        led.problem()

def _exception(  module, message, exception ):
    # Count exceptions as errors
    _glb.error_count += 1
    import led 
    led.problem( )

    s = _formatRecord( module, EXCEPTION, message )
    # Format exception to a string
    bytefile = io.BytesIO()
    sys.print_exception( exception, bytefile )
    exception_text = bytefile.getvalue().decode( )
    exception_text = "       " + exception_text.replace("\n", "\n       " )
    # Output exception to console and file
    print(s)
    print( exception_text )
    with open( _glb.current_log_filename, "a") as file:
        file.write( s )
        file.write( "\n" )
        file.write( exception_text )
        file.write( "\n" )
        _glb.current_logfile_size += len(s) + len(exception_text) + 2
    _check_max_logfile_size()
    
   
def _get_error_count( ):
    return _glb.error_count

t0 = time.ticks_ms()

class Logger:
    # This class is the public interface to minilog
    def __init__( self, module ):
        self.module = module
        
    def debug( self, message ):
        _log( self.module, DEBUG, message )

    def info( self, message ):
        _log( self.module, INFO, message )

    def error( self, message ):
        _log( self.module, ERROR, message )

    def exc( self, exception, message ):
        _exception( self.module, message, exception )
        
    def mem( self, message ):
    
        if _LOG_MEMORY:
            # This can be very slow with 8MB of memory (100-200msec)
            gc.collect()
            _log( self.module, INFO, f"{message} {gc.mem_free():.0f} bytes")
    
    def get_filename( self ):
        return _glb.current_log_filename
        
    def get_error_count( self ):
        # Error count since reboot
        return _get_error_count()

    def timeline( self, message ):
        global t0
        t = time.ticks_ms()
        dt = time.ticks_diff( t, t0 )
        _log( self.module, DEBUG, f"dtime {dt} {message} ")
        t0 = t
           
# To start a logger in a module use 
# from minilog import getLogger
# logger = getLogger( __name __ )

def getLogger( module ):
    return Logger( module )

def set_time_zone_offset( hours ):
    _glb.tzoffset = int( hours * 3600 )
    
_init()   
