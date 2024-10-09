import os
from microdot import send_file
import time

from tunemanager import tunemanager
import fileops

DESTINATION_FOLDERS = {
    "mid": "/tunelib",
    "main.py": "",
    "json": "/data",
    "pinout.txt": "/data",
    "py": "/software/mpy",
    "mpy": "/software/mpy",
    "html": "/software/static",
    "js": "/software/static",
    "css": "/software/static",
    "ico": "/software/static",
    "png": "/software/static",
    "jpg": "/software/static",
    "gz": "/software/static"
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
def get_mime_type( filename ):
    try:
        part = -1
        if filename.endswith(".gz"):
            part = -2
        return MIME_TYPES[filename.split(".")[part]] + ";charset=UTF-8"
    except (IndexError, KeyError):
        return "text/plain;charset=UTF-8"

def listdir(path):
    def get_date( filename ):
        t = time.localtime(os.stat(filename)[7])
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
        # Sort files to destination folder depending on name/file extension
        folder = DESTINATION_FOLDERS.get( filename, 
                    DESTINATION_FOLDERS.get( filename.split(".")[-1].lower(), None)
                                        )
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

    if "tunelib/" in path and path.lower().endswith( ".mid" ):
        tunemanager.remember_to_sync_tunelib()

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
                     compressed=filename.endswith(".gz") )


def status():
    stat = os.statvfs('/')
    return {
        'total_flash': stat[0]*stat[2],
        'used_flash': stat[0]*(stat[2]-stat[3])
    }

def delete(path):
    os.remove(path)
    if "tunelib/" in path and path.lower().endswith(".mid"):
        # Deleting MIDI file requires sync of tunelib at next reboot
        tunemanager.remember_to_sync_tunelib()

def get_midi_file( request_path ):
    filename = "/tunelib/" + request_path
    return send_file(filename,
                     content_type=get_mime_type("mid") )
