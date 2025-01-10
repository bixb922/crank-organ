import os
from microdot import send_file
import time

from drehorgel import tunemanager
import fileops
# >>> allow sync instead of copy?
# >>> allow 2 tunelib folders, for staging?
# >>> compare tunelib.json with tunelib folder?

DESTINATION_FOLDERS = {
    "mid": "/tunelib",
    "main.py": "", # special case
    "json": "/data",
    "txt": "/data", # pinout.txt
    "py": "/software/mpy",
    "mpy": "/software/mpy",
    "html": "/software/static",
    "js": "/software/static",
    "css": "/software/static",
    "ico": "/software/static",
    "png": "/software/static",
    "jpg": "/software/static",
}

MIME_TYPES = {
    # default is text/plain;charset=UTF-8 
    "json": "application/json;charset=UTF-8",
    "gif": "image/gif",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "ico": "image/vnd.microsoft.icon",
    "mid": "audio/midi",
    "html": "text/html",
    "css": "text/css",
    "js": "javascript"
}

def _check_midi_file( path ):
    if "tunelib/" in path and fileops.get_file_type( path ) == "mid":
        # Deleting MIDI file requires sync of tunelib at next reboot
        tunemanager.remember_to_sync_tunelib()

def get_mime_type( filename ):
    # Default MIME type is text/plain
    return MIME_TYPES.get( fileops.get_file_type(filename), "text/plain")  + ";charset=UTF-8"

def listdir(path):
    def get_date( filename ):
        try:
            t = time.localtime(os.stat(filename)[7])
        except OverflowError:
            # This really happened.... the cause
            # is that a file got transferred with /filemanager
            # without having
            # set the ntp time. Since the time zone offset was minus 3 hours
            # this gives a negativetime. 
            # C language interpreted that negative number as
            # unsigned int.
            # This means: 
            # -3 hrs plus some == -10441 == 0xffffd737 == 4294956855
            # which is far, far in the future... overflow.
            return "2000-01-01 00:00"
        return f"{t[0]:4d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}"

    if not path.endswith("/"):
        path += "/"
    # 16384 means "folder" or "directory"
    # 32768 means file

    if not fileops.is_folder( path ):
        return []
    return [ {"name":inode[0], 
              "isDirectory":1 if inode[1]==16384 else 0, 
              "size":inode[3], 
              "path":path+inode[0],
              "date":get_date(path + "/" + inode[0]) if inode[1]!=16384 else ""
              }
             for inode in os.ilistdir(path) ]


def upload( request, path, filename  ):
    # Upload a file from the PC to the microcontroller

    # Javascript must use String.normalize() for filenames
    # See filemanager.html encodePath()
    # If not Hände can be encoded H\xc3\xa4nde
    # or Ha\xcc\x88nde (combined a + diacritics mark)
    # normalize() substitutes combined diacritics
    # to code points.

    if path != "__auto__":
        folder = path
    else:
        # automatic path
        # Sort files to destination folder depending on file type
        # But main.py has it's special folder!
        # So try with the filename first, then with type:
        folder = DESTINATION_FOLDERS.get( 
                    filename,
                    DESTINATION_FOLDERS.get( fileops.get_file_type( filename ) ) )
                                        
    if folder is None:
        raise ValueError

    path = folder + "/" + filename
   
    try:
        old_file_size = os.stat(path)[6]
    except OSError:
        old_file_size = None
    with open(path, "wb") as file:
        data = request.body
        new_file_size = len(data)
        file.write( data )

    _check_midi_file( path )

    # If a compressed file is replaced with a uncompressed one
    # delete the replaced file. Same with .py and .mpy
    # And vice-versa. Only one instance of two equivalent
    # files will be allowed, to avoid duplicity and confusion.
    equiv = fileops.get_equivalent( path )
    if fileops.file_exists( equiv ):
        # The equiv file is replaced by the new file
        os.remove( equiv )
        
    return {"folder": folder, 
            "oldFileSize": old_file_size,
            "newFileSize": new_file_size }


def download(path):
    # Download a file from the microcontroller to the PC

    def serve_file( path ):
        buffer = bytearray(10000)
        mvb = memoryview(buffer)
        with open(path, "rb") as file:
            while True:
                length = file.readinto(buffer)
                if not length:
                    break
                yield mvb[0:length]

    filename = path.split("/")[-1]
    
    return serve_file(path), 200, {
        "Content-Type": "application/octet-stream",
        "Content-Disposition": f'attachment; filename="{filename}"'}



def _formatLogGenerator(filename):
    def escapeHtml( s ):
        return s.replace("&","&amp;")\
            .replace("<","&lt;")\
            .replace(">","&gt;")\
            .replace("'","&apos;")\
            .replace('"',"&quot;")\
            
    def log_generator():
        # Format log as HTML
        with open(filename) as file:
            yield "<!DOCTYPE html><head></head><body><title>Error log</title>"
            yield "<body><table>"
            while True:
                s = file.readline()
                if s == "":
                    break
                if s[0:1] == " ":
                    # This happens for exception traceback, put traceback info in column 3
                    yield "<tr><td></td><td></td><td></td><td>"
                    yield escapeHtml(s) 
                    yield "</td></tr>"
                else:
                    yield "<tr>"
                    for p in s.split(" - "):
                        yield "<td>" 
                        yield escapeHtml(p)
                        yield "</td>"
        yield "</table></body>"

    return log_generator(), 200, {"Content-Type": "text/html; charset=UTF-8"}



def show_file( filename ):
    
    if not fileops.file_exists( filename ):
        return "", 404
    
    if filename.endswith(".log"):
        return _formatLogGenerator( filename )
    
    # Don't render html, show everything as plain text.
    # Allow to show compressed files, let browser uncompress
    ct = "text/plain"
    if ".json" in filename:
        ct = "application/json"
    ct += ";charset=UTF-8"
    return send_file( filename, 
                     content_type=ct, 
                     compressed=fileops.is_compressed( filename ) )


def status():
    stat = os.statvfs('/')
    return {
        'total_flash': stat[0]*stat[2],
        'used_flash': stat[0]*(stat[2]-stat[3])
    }

def delete(path):
    os.remove(path)
    _check_midi_file( path )

def get_midi_file( request_path ): 
    physical_name = fileops.find_decompressed_midi_filename( "/tunelib/" + request_path )
    return send_file( physical_name,
                     content_type=get_mime_type("mid") )
