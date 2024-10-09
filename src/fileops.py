# (c) 2023 Hermann Paul von Borries
# MIT License
from micropython import const
import json
import asyncio
import errno
import os

import scheduler

KEEP_OLD_VERSIONS = const(3)

def backup(filename):
    # organtuner: for each note tuned
    # pinout: only when saving user input
    # config: when saving user input.
    #        Encrypt password has no backup
    # tunemanager: when updating tunelib and when saving
    #              user data.
    #              Updating history has no backup.
    from timezone import timezone
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
    folder = filename[0 : -len(path[-1])]
    matched_files = []
    # Search for filenames like "config.json-2023-10-23"
    # Compare strings up to the "-", i.e. "config.json-"
    search_for = filename + "-"
    for fn in os.listdir(folder):
        f = folder + fn
        if f[0 : len(search_for)] == search_for:
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
    try:
        os.mkdir( folder )
    except OSError:
        pass

def is_folder( folder_name ):
    return os.stat( folder_name )[0] == 16384