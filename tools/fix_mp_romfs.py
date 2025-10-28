# Fix MicroPython .bin image generation for romfs
# Needs v1.26
    # git clone https://www.github.com/micropython/micropython.git
	# To generate micropython 1.26.preview image:
	# % git rebase -i f77fd62
    # and edit file with vi (or whatever editor git uses)
	# to remove first line which is commit d737112 "esp32/esp32_common.cmake: Use the tinyusb source files from ESP-IDF"
	# Copy manifest.py and boot.py to some folder without spaces, for example ~/
    # Adjust folders in this program, run fix_mp_romfs.py
    # to add partitions file and define necessary compilation flags. 
    # Establish esp-idf:
    # % cd esp-idf
    # % source export.sh
    #
    # Compile mpy-cross
    # % cd micropython
    # % make -C mpy-crosss
    #
    # run this program to enable romfs:
    # % python3 crank-organ/tools/fix_mp_romfs.py
    #
    # Copy manifest.py and boot.py to a folder with no spaces
    # Compile micropython:
    # % cd micropython/ports/esp32
	# % rm -f -r build-ESP32_GENER* folders
	# % make clean	
	# % make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT submodules
    # No spaces allowed in FROZEN_MANIFEST path (even if enclosed in "")
	# % make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT FROZEN_MANIFEST=/some_path_without_blanks/manifest.py
    # The output are the .bin files
    # .bin files are now in micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT folder
    # Copy to micropython_bin folder with 
    # % gmake copy_mp_bin

from pathlib import Path
from shutil import copy

home_path = Path.home()
port_path = home_path / "micropython/ports/esp32"
my_path = Path(__file__).parent
board_path = port_path / "boards/ESP32_GENERIC_S3"
print(f"{home_path=}")
print(f"{port_path=}")
print(f"{my_path=}")
PARTITION_FILENAME = "partitions-4MiB-BIG-romfs.csv"

def add_partition_csv():
    partition_dst = port_path / PARTITION_FILENAME
    copy( my_path / PARTITION_FILENAME, partition_dst )
    print("new partition csv copied to", partition_dst)

def fix_sdkconfig_board():
    sdkconfig_filename = board_path / "sdkconfig.board"
    with open( sdkconfig_filename ) as input:
        sdkconfig = input.read()

    if "CONFIG_PARTITION_TABLE_CUSTOM" in sdkconfig:
        print(f"{sdkconfig_filename} already up to date")
        return
    sdkconfig += "\nCONFIG_PARTITION_TABLE_CUSTOM=y\n"
    sdkconfig += f'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="{PARTITION_FILENAME}"\n'
    with open( sdkconfig_filename, "w") as output:
        output.write( sdkconfig )
    print(f"{sdkconfig_filename} updated")

def fix_mpconfigboard():
    mpconfig_filename = board_path / "mpconfigboard.h"
    with open(mpconfig_filename ) as input:
        mpconfigport = input.read()

    if "MICROPY_VFS_ROM" in mpconfigport:
        print(f"{mpconfig_filename} already up to date")
        return
    
    mpconfigport += "\n#define MICROPY_VFS_ROM (1)\n"
    with open( mpconfig_filename, "w" ) as output:
        output.write( mpconfigport )
    print(f"{mpconfig_filename} updated")
    
def main():
    add_partition_csv()
    fix_sdkconfig_board()
    fix_mpconfigboard()

main()

# Flash saved by using romfs:
# mpy=42 files, 130,384 bytes net, 229,376 bytes on flash
# static=16 files, 78,776 bytes net, 106,496 bytes on flash. 
# Total=327.000 bytes on flash/8k avg for midi.gz file=41 MIDI files

# Start time 1500 MIDI files, software on vfs, vfs.readsize=4096
# Total startup time (without main, until asyncio ready) 6145 msec
# Memory used at startup 224736
# gc time from 47 to 200 msec

# Start time 1500 MIDI files, software on romfs:
# Total startup time (without main, until asyncio ready) 4373 msec
# Memory used at startup 130192
# gc time from 17 to 60 msec
