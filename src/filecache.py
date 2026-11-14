# (c) Copyright 2026 Hermann Paul von Borries
# MIT License

# Provides a  MIDI file cache
# Purpose: speed up MIDI file handling of umidiparser

import os
from deflate import DeflateIO, AUTO

import fileops
from minilog import getLogger
_logger = getLogger(__name__)


_DECOMPRESSED_FILE_NAME = const("/data/midi_cached.mid")
class MidiFileCache:
    # Compressed files are decompressed and cached in _DECOMPRESSED_FILE_NAME
    # Uncompressed MIDI files are used "as is"
    # Allow for one cached MIDI file and it's metadata (tunelib row)
    cached_filename = None
    cached_metadata = None
    # For cache in flash file
    cached_data =  None # shows where the data is, either xyzzy.mid or _DECOMPRESSED_FILE_NAME

    @classmethod
    def prepare( cls, filename, metadata ):
        if filename == cls.cached_filename and cls.cached_metadata:
            # Already cached, metadata also cached.
            return

        if fileops.is_compressed( filename ):
            #  Decompress to /data/midi_cached.mid
            cls.cached_data = _DECOMPRESSED_FILE_NAME
            with open( filename, "rb") as file:
                with DeflateIO(file, AUTO, 0, True) as stream: # type:ignore
                    with open( _DECOMPRESSED_FILE_NAME, "wb") as output:  # type:ignore
                        output.write(stream.read())
        else:
            # The data is in the original MIDI file, no need to copy/decompress
            cls.cached_data = filename
        # This is the filename that is now in cache
        cls.cached_filename = filename
        cls.cached_metadata = metadata

    @classmethod
    def get_metadata(cls):
        # tunelib entry of cached MIDI file
        return cls.cached_metadata

    @classmethod
    def clear(cls):
        cls.cached_filename = None
        cls.cached_metadata = None
        try:
            # Not strictly necessary
            os.remove(_DECOMPRESSED_FILE_NAME)
        except:
            pass

    def __init__( self, filename ):
        if filename != self.cached_filename:
            self.prepare( filename, None ) # No metadata in this case
        self.fileobject = open( self.cached_data, "rb")
        self.filename = filename
        
    def open( self ):
        return _FileInstance( self.fileobject )
            
    def finalize( self ):
        # Allow caller to control when the the physical file
        # can be closed.
        self.fileobject.close()
        # From now on, any attempt to use the file will raise a ValueError

    def get_filename( self ):
        return self.filename
    
class _FileInstance:
    # An open file instance. There may be several instances open at
    # the same time. Holds the current position (of this instance)
    # in the file.
    def __init__( self, fileobject ):
        self.fileobject = fileobject
        self.position = 0

    def __enter__( self ):
        # No additional housekeeping necessary. The underlying file is closed
        # when the next file is opened, see self.finalize(). But __enter__
        # and __exit__ allow it to use "with MidiFileCache.open()" just like "with open()"
        return self

    def __exit__( self, exc_type, exc_val, exc_traceback ):
        # Return None to raise any exception
        return
    
    # Since many readers use the same file object, 
    # the current position in the file must be managed separately.
    # The _FileInstance must keep track of the position.
    def readinto( self, buffer ):
        fo = self.fileobject
        fo.seek( self.position )
        n = fo.readinto( buffer )
        self.position = fo.tell()
        return n
    
    def read( self, length ):
        fo = self.fileobject
        fo.seek( self.position )
        data = fo.read( length )
        self.position = fo.tell()
        return data
    
    def seek( self, offset, whence=0 ):
        if whence == 0:
            self.position = offset
        elif whence == 1:
            self.position += offset
        else: # whence == 2, not used
            raise NotImplementedError
            # relative to the end of file.
            # fo = self.fileobject
            # fo.seek( 0, 2 )
            # self.position = fo.tell() + offset
            
    def tell( self ):
        return self.position
    
    def byte_reader(self, initial_position, length, buffer_size ):
        # Generator to read portions of buffer_size bytes from a MIDI file track
        # and then return byte by byte.
        # Reading is limited from initial_position to
        # initial_position+length of the track. 
        # This allows to read a track chunk of a MIDI file
        # and get a end of file condition when the track chunk is fully read.
        # There is a _FileInstance (and a byte_reader) for each track
        # of the MIDI file.

        # Allocate buffer to be reused for each read
        buffer = bytearray(buffer_size)
        self.seek(initial_position)
        unread_bytes = length
        while True:
            # Read a buffer of data and yield byte by byte to caller
            bytes_read =  self.readinto(buffer)
            unread_bytes -= bytes_read
            yield from memoryview(buffer)[0:bytes_read]
            # Check if end of track reached
            if unread_bytes <= 0 or bytes_read <= 0:
                break
        # StopIteration if caller gets here.

    # REPLACE THIS IN _FileInstance
    # def byte_reader(self, initial_position, length, buffer_size ):
    #     # buffer_size not not needed here, this is much faster.
    #     yield from memoryview(self.fileobject.getvalue())[initial_position:initial_position+length]
# _FileInstance.readinto may be unused if this bytereader is used..

_logger.debug("MIDI file cache decompresses to flash")


# No common superclass since only one MidiFileCache class should be present
# RAM cache: for future use, not in use now.
# _FileInstance is optimized with new byte_reader()
# import io
# class MidiFileCache:
#     # Allow for one cached MIDI file and it's metadata (tunelib row)
#     cached_filename = None
#     cached_metadata = None

#     cached_data =  bytearray(50_000) # automatically increased if larger files are cached.
#     cached_size = 0

#     @classmethod
#     def prepare( cls, filename, metadata ):
#         if filename == cls.cached_filename and cls.cached_metadata:
#             # Already cached. With no metadata: that was an occasional use, not a regular cache operation.
#             return
#         while True:
#             if fileops.is_compressed( filename ):
#                 with open( filename, "rb") as file:
#                     with DeflateIO(file, AUTO, 0, True) as stream: # type:ignore
#                        size = stream.readinto(cls.cached_data)
#             else:
#                 with open( filename, "rb")  as file:
#                     size = file.readinto(cls.cached_data)
#             if size < len(cls.cached_data):
#                 # Data did fit correctly into buffer.
#                 break
#             # Make buffer a bit larger, to accomodate requested file size
#             new_size = round(len(cls.cached_data)*1.3)
#             _logger.info(f"file {filename} did not fit into buffer, increasing from {len(cls.cached_data)} to {new_size}" )
#             cls.cached_data = bytearray( new_size )
#         #  This is what is is now in the cache
#         cls.cached_filename = filename
#         cls.cached_metadata = metadata
#         cls.cached_size = size

#     @classmethod
#     def get_metadata(cls):
#         return cls.cached_metadata

#     @classmethod
#     def clear(cls):
#         cls.cached_filename = None
#         cls.cached_metadata = None

#     def __init__( self, filename ):
#         if filename != self.cached_filename:
#             self.prepare( filename, None ) # No metadata in this case

#         self.fileobject = io.BytesIO(memoryview(self.cached_data)[0:self.cached_size])
#         self.filename = filename

#     def open( self ):
#         return _FileInstance( self.fileobject )
           
#     def finalize( self ):
#         # Allow caller to control when the the physical file
#         # can be closed.
#         self.fileobject.close() 

#     def get_filename( self ):
#         return self.filename

# _logger.debug(f"MIDI file cache in RAM, initial buffer size={len(MidiFileCache.cached_data)} bytes")
# For transition delete remaining midi files in /data
