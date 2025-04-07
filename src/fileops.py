# (c) 2023 Hermann Paul von Borries
# MIT License
from micropython import const
import json
import asyncio
import errno
import os
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
                return json.load(file)
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

def is_folder( folder_name ):
    return os.stat( folder_name )[0] == 16384

def find_decompressed_midi_filename( filename ):
    # Will first return .mid file, if it exists.
    # iI not, will add .gz (if not present) and
    # then try to open .mid.gz file
    # If not found: OSError
    # So it will open the midi file, disregarding if its foo.mid
    # or foo.mid.gz
    if file_exists( filename ) and not is_compressed(filename):
        return filename
    # Decompress in one go, there is enough RAM
    # and it will be freed immediately
    # Using ByteIO is faster but would require changes in umidiparser
    # Or else, use a RAM disk, with higher gc.collect() times
    with open( filename, "rb") as file:
        with DeflateIO(file, AUTO, 0, True) as stream: # type:ignore
            data = stream.read()

    # This code does not allow have two MIDI files open at the same time.
    # Also: temp.mid does not get deleted after use, it remains there
    # until the next file is decompressed.
    TEMP_FILENAME = "/data/temp.mid"
    with open( TEMP_FILENAME, "wb") as output:  # type:ignore
        output.write(data)
    return TEMP_FILENAME

def open_midi( filename ):
    # Restriction: find_decompressed_midi_filename() works only
    # for one file at a time. Cannot open 2 MIDI files simultaneously.
    # (but that is not required here)
    from umidiparser import MidiFile
    # With 4 to 8 MB RAM, there is enough to have large buffer.
    # But even so, there is no need to read the full file to memory
    # A buffer size of > 1000 means almost no impact on CPU and
    # uses a relatively small amount of RAM
    # >>> could push decompress to MidiFile() and decompress on the
    # fly, but that would require buffer_size=0 (i.e. buffer complete file)
    return MidiFile(find_decompressed_midi_filename( filename ),
                    buffer_size=5000,
                    reuse_event_object=True)

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
    if is_compressed( filename ):
        return filename[:-3]
    return filename
