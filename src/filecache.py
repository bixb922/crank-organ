# (c) Copyright 2026 Hermann Paul von Borries
# MIT License

# Provides a very basic file cache
# Purpose: speed up MIDI file handling of umidiparser
class MidiFileCache:
    def __init__( self, filename ):
        self.fileobject = open( filename, "rb" )
        self.filename = filename
        
    def open( self ):
        return _FileInstance( self.fileobject )
            
    def finalize( self ):
        # Allow caller to control when the the physical file
        # can be closed.
        self.fileobject.close()
        # From now on, any attempt to use the file will raise a ValueErro

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
    
    # umidiparser needs both readinto and read.
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
        # initial_position + length of the track. 
        # This allows to read a track chunk
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
