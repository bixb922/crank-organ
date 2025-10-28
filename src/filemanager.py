import os
from microdot import send_file

from drehorgel import tunemanager, config
import fileops


# Compress midi, html, css and js files in the browser: NO, bad idea.
# >>> show compilation date on filemanager root to aid software upload.

DESTINATION_FOLDERS = {
    "mid": config.TUNELIB_FOLDER,
    "main.py": "/", # special case
    "json": "/data/",
    "txt": "/data/",
    "py": "/software/mpy/",
    "mpy": "/software/mpy/",
    "html": "/software/static/",
    "js": "/software/static/",
    "css": "/software/static/",
    "ico": "/software/static/",
    "png": "/software/static/",
    "jpg": "/software/static/",
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

def _check_midi_file( path, file_size=-1 ):
    # Check if file operation affected a MIDI file.
    # If so, queue a file update or deletion in tunemanager.
    # This is used to keep the tunelib.json in sync with the file system.
    # If the file is deleted, file_size will be -1.
    if "tunelib/" in path and fileops.get_file_type( path ) == "mid":
        # Changing or deleting MIDI file requires sync of tunelib at next reboot
        if file_size >= 0:
            tunemanager.queue_file_updated( path, file_size )
        else:
            tunemanager.queue_file_deleted( path )

def get_mime_type( filename ):
    # Default MIME type is text/plain
    return MIME_TYPES.get( fileops.get_file_type(filename), "text/plain")  + ";charset=UTF-8"

def listdir(path):
    if not path.endswith("/"):
        path += "/"
    listing = fast_listdir(path)
    if path == "/tunelib/":
        # Speed up /tunelib folder, dates are already in tunelib.json.
        tunelibfd = tunemanager.file_date_dict()
    else:
        tunelibfd = dict() # tunelibfd only available for files in /tunelib folder
    getdate = 0
    for fileinfo in listing:
        date = tunelibfd.get(fileinfo["name"], "") 
        # Show date for up to 100 files, if not, response
        # time becomes slow.
        # This maximum does not apply to tunelib.
        # 100 files can take about 4 seconds due to os.stat()
        if not date and getdate<100:
            date = fileops.get_file_date(path + fileinfo["name"])
            getdate += 1
        fileinfo["date"] = date
    return listing

def fast_listdir(path):
    # This function could be used in a webservice to get a faster
    # listing of file information. 
    if not fileops.is_folder( path ):
        return []
    # 16384 means "folder" or "directory"
    # 32768 means file
    # /rom returns ('rom', 16384, 0)
    # whereas other notes return   ('data', 16384, 0, 0)

    def get_size( dir_entry ):
        try:
            return dir_entry[3]  # size in bytes
        except IndexError:
            # This happens for /rom, which has no size
            return 0
        
    return [{
              "name":dir_entry[0], 
              "isDirectory":1 if dir_entry[1]==16384 else 0, 
              "size": get_size( dir_entry), 
              "path":path+dir_entry[0],
              "date":""
              } for dir_entry in os.ilistdir(path)]
        
def upload( request, path, filename  ):
    # Upload a file from the PC to the microcontroller

    # Javascript must use String.normalize("NFC") for filenames
    # See filemanager.html encodePath()
    # If not normalized, "Hände" can be encoded either:
    # "H\xc3\xa4nde "(this is desirable, Code point for a umlaut, chr(0xe0)
    # "Ha\xcc\x88nde" (this is not desirable, combined a + diacritics mark)
    # Here \xcc\x88 = U+308 = "\u0308" is the diacritics mark, 
    # and it is rendered top of the a.
    # Other diacritics marks: \u0300 to \u036f
    # And we want to have it normalized to NFC! (Code points)
    # Javascript normalize("NFC") substitutes combined diacritics
    # to code points.
    
    # test for diacritics marks, these must be filtered for consistency Mac/Windows/Javascript/MicroPython/browsers
    for z in filename:
        if 0x300 <= ord(z) <= 0x36f:
           print(filename.encode())
           raise RuntimeError(f"Diacritical mark  found in {filename}")
        
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
        # Create folder if it does not exist
        fileops.make_folder( folder )   

    if folder is None:
        raise ValueError

    path = folder + filename
   
    try:
        old_file_size = os.stat(path)[6]
    except OSError:
        old_file_size = None
    with open(path, "wb") as file:  # type:ignore
        data = request.body
        new_file_size = len(data)
        file.write( data )

    _check_midi_file( path, new_file_size )

    # If a compressed file is replaced with a uncompressed one
    # delete the replaced file. Same with .py and .mpy
    # And vice-versa. Only one instance (the newer) of two equivalent
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
    # Serve file in chunks of 10kB
    def serve_file( path ):
        buffer = bytearray(10000)
        mvb = memoryview(buffer)
        with open(path, "rb") as file:
            while True:
                length = file.readinto(buffer)
                if not length:
                    break
                yield mvb[0:length]

    filename = fileops.get_basename(path)
    
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

    # Generator function to yield log lines
    def log_generator():
        # Format log as HTML
        with open(filename) as file:
            yield "<!DOCTYPE html><head></head><body><title>Error log</title>"
            yield '<body><table>'
            current_date = "***"
            while True:
                s = file.readline()
                if s == "":
                    break
                if s[0:1] == " ":
                    # This happens for exception traceback, 
                    # put traceback info in column 3
                    yield "<tr><td></td><td></td><td></td><td>"
                    yield escapeHtml(s) 
                    yield "</td></tr>"
                else:
                    p = s.split(" - ")
                    dateparts = p[0].split(" ")
                    if len(dateparts) == 1:
                        # If time is not synchronized show "No Date"
                        t = p[0]
                        d = "No date"
                    else:
                        d, t = dateparts

                    if d != current_date:
                        # Show date once only
                        yield "<tr><td style='font-size:large;font-weight:bold;text-wrap:nowrap;'>" + d + "</td></tr>"
                        current_date = d

                    yield "<tr>"
                    try:
                        yield "<td style='text-wrap:nowrap;'>" + t + "</td>"
                        yield "<td>" + p[1] + "</td>"
                        yield "<td>" + p[2] + "</td>"
                        yield "<td>" + escapeHtml( " - ".join(p[3:]) ) + "</td>"
                    except IndexError:
                        pass
                    yield "</tr>"
        yield "</table></body>"

    return log_generator(), 200, {"Content-Type": "text/html; charset=UTF-8"}



def show_file( filename ):
    
    if not fileops.file_exists( filename ):
        return "", 404
    
    if filename.endswith(".log"):
        return _formatLogGenerator( filename )
    
    # Don't render html, show everything as plain text.
    # Allow to show compressed files, let browser uncompress
    # Mark json files, some browsers (Chrome) pretty print json
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
    physical_name = fileops.find_decompressed_midi_filename( config.TUNELIB_FOLDER + request_path )
    return send_file( physical_name,
                     content_type=get_mime_type("mid") )


def purge_tunelib_file( fn ):
    def append( fn, n ):
        if n:
            fn += f"_({n})"
        return fn
   
    fileops.make_folder( config.PURGED_FOLDER )
    n = 0
    from_fn = config.TUNELIB_FOLDER + fn
    to_fn = config.PURGED_FOLDER + fn
    # Don't overwrite existing files in "purged" folder
    while fileops.file_exists( append(to_fn, n) ):
        n += 1
        if n > 10:
            raise RuntimeError(f"Too many purged file versions {fn=} {n=}")
    _check_midi_file( from_fn )
    os.rename( from_fn, append(to_fn, n) )
   
