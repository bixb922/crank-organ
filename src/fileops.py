# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
from micropython import const
import json
import asyncio
import errno
import os
import time

from deflate import DeflateIO, AUTO
import scheduler

KEEP_OLD_VERSIONS = const(2)

def backup(filename):
    # organtuner: for each note tuned
    # pinout: only when saving user input
    # config: when saving user input.
    #        Encrypt password has no backup
    # tunemanager: when updating tunelib and when saving
    #              user data.
    #              Updating history has no backup.
    from drehorgel import timezone
    if not file_exists(filename):
        return
    # Make a daily backup
    backup_filename = f"{filename}-{timezone.now_ymd()}"
    if not file_exists(backup_filename):
        os.rename(filename, backup_filename)

    # Purging old backup files doesn't need to be done
    # immediately, do it a bit later...
    asyncio.create_task(delete_old_versions(filename))

def file_exists(filename):
    try:
        open(filename).close()
        return True
    except OSError:
        return False

def folder_exists(folder):
    # Check if folder exists, i.e. is a directory
    try:
         open(folder).close()
    except OSError as e:
        return e.errno == errno.EISDIR

def read_json(filename, default=None, recreate=False):
    # Read json file, or backups if error.
    # If not found or wrong format, and backups fail:
    #   if default: will return the default
    #   if recreate and default: will rewrite the file, no backup
    #   else: raise error
    try:
        with open(filename) as file:
            return json.load(file)
    except (OSError, ValueError):
        # Will raise OSError(ENOENT) if no file found
        try:
            f = find_latest_backup(filename)
            with open(f) as file:
                j = json.load(file)
                print(f"fileops.read_json using backup file {f}")
                return j
        except (OSError, ValueError):
            if default is not None:
                if recreate:
                    write_json( default, filename )
                return default
            raise


def write_json(json_data, filename, keep_backup=True):
    if keep_backup:
        backup(filename)
    with open(filename, "w") as file:
        json.dump(json_data, file)


async def delete_old_versions(filename):
    # Request time slice and wait indefinitely for it.
    async with scheduler.RequestSlice("backup", 500):
        matched_files = get_all_backup_files(filename)
        while len(matched_files) > KEEP_OLD_VERSIONS:
            await asyncio.sleep_ms(1)
            delete_file = matched_files.pop(0)
            os.remove(delete_file)
            print("fileops - old backup file deleted", delete_file)


def get_all_backup_files(filename):
    path = filename.split("/")
    # Folder is everything except the last element of path
    folder = filename[0 : -len(path[-1])]
    matched_files = []
    # Search for filenames like "config.json-2023-10-23"
    # Compare strings up to the "-", i.e. "config.json-"
    search_for = filename + "-"
    # ilistdir() takes same time as listdir(). 
    for fn in os.listdir(folder):
        f = folder + fn
        if f.startswith( search_for ):
            matched_files.append(f)
    matched_files.sort()
    return matched_files

def find_latest_backup(filename):
    matched_files = get_all_backup_files(filename)
    if len(matched_files) == 0:
        raise OSError(errno.ENOENT)
    return matched_files[-1]

def make_folder( folder ):
    # Create folder if not there
    if folder.endswith("/"):
        folder = folder[:-1]
    try:
        os.mkdir( folder )
    except OSError:
        pass

def copy_file( source, destination ):
    # Copy file from source to destination
    # If destination exists, it will be overwritten.
    # If source does not exist, OSError is raised.
    with open(source, "rb") as src:
        with open(destination, "wb") as dst: # type:ignore
            dst.write(src.read())

def copy_folder( src_folder, dst_folder, overwrite=False ):
        for fn in  os.listdir(src_folder):
            src_file = src_folder + "/" + fn
            dst_file = dst_folder + "/" + fn
            if overwrite or not file_exists(dst_file):
                copy_file(src_file, dst_file)


def is_folder( folder_name ):
    return os.stat( folder_name )[0] == 16384

def decompress_midi( filename, temp_filename ):
    # Will first return filename of .mid file, if it exists.
    # iI not, will add .gz (if not present) and
    # then try to decompress the .mid.gz file and return the temp_filename
    # of the decompressed .mid.gz file.
    # If not found: OSError
    if file_exists( filename ) and not is_compressed(filename):
        return filename
    # Decompress in one go, there is enough RAM
    # and RAM will be freed immediately. Store in flash.
    # Caching the decompressed file in RAM would raise gc.collect() times.
    with open( filename, "rb") as file:
        with DeflateIO(file, AUTO, 0, True) as stream: # type:ignore
            data = stream.read()

    # Also: temp_filename does not get deleted after use, it remains there
    # until the next file is decompressed.
    with open( temp_filename, "wb") as output:  # type:ignore
        output.write(data)
    return temp_filename

def open_midi( filename ):
    # Reading the whole file to memory (buffer_size=0) makes garbage
    # collection times much higher.
    # With filecache=True, 500 bytes is appropriate. There is a minor
    # gain with 1000 bytes in terms of overall performance
    # but open/first note times increase with 1000 to 5000 bytes.
    # Also: 500 bytes per track keeps gc times low.
    from umidiparser import MidiFile
    # Files should be decompressed at this point. But there is very little overhead
    # in calling decompress_midi for MIDI file that is already decompressed.
    return MidiFile( decompress_midi( filename, "/data/midi_fileops.mid"),
                    buffer_size=100,
                    reuse_event_object=True )

def get_file_type( filename ):
        # foo.mid.gz returns "mid"
        # foo.mid returns "mid"
        # foo.MID returns "mid"
        # Also works with .html, .json, .html.gz etc.
        parts = filename.split(".")
        keep = -1
        if is_compressed( filename ):
            keep = -2
        return parts[keep].lower()

def is_compressed( filename ):
    return filename.endswith(".gz")

def get_filename_stem( filename ):
    # Get the name minus folders minus filetype minus .gz
    parts = filename.split("/")
    # Disregard folders in filename
    fn = parts[-1]
    parts = fn.split(".")
    keep = -1
    if is_compressed( filename ):
        keep = -2
    return ".".join( parts[0:keep] )

def get_basename( path ):
    return path.split("/")[-1]

def get_equivalent( filename ):
    # For foo.mpy return foo.py
    # For foo.py return foo.mpy
    # For foo.bar.gz return foo.bar
    # For foo.bar return foo.bar.gz
    # No test is made to see if these files exist.
    if is_compressed( filename ):
        return filename[0:-3] # get rid of the .gz
    ft = get_file_type( filename )
    if ft == "mpy":
        return filename[0:-3] + "py"
    if ft == "py":
        return filename[0:-2] + "mpy"
    # Its a non-python uncompressed file:
    return filename + ".gz"

def filename_no_gz( filename ):
    # if is_compressed( filename ):
    if filename.endswith(".gz"):
        return filename[:-3]
    return filename

def get_file_date( filename ):
    try:
        t = time.localtime(os.stat(filename)[7])
    except OverflowError:
        # This really happened.... the cause
        # is that a file got transferred with /filemanager
        # without having
        # set the ntp time. Since the time zone offset was minus 3 hours
        # this gives a negative time. 
        # C language interpreted that negative number as
        # unsigned int.
        # This means: 
        # -3 hrs plus some == -10441 == 0xffffd737 == 4294956855
        # which is far, far in the future... fortunately raises overflow.
        return "2000-01-01 00:00"
    return f"{t[0]:4d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}"



def get_mime_type( filename ):
    mime_types = {
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
        "txt": "text/text",
        "js": "javascript"
    }
    # Default MIME type is text/plain
    return mime_types.get( get_file_type(filename), "text/plain")  + ";charset=UTF-8"
