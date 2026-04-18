# Fix MicroPython .bin image generation for romfs
# version > v1.26
# Get esp-idf, see: https://github.com/micropython/micropython/tree/master/ports/esp32
    # git clone ...
    # no need for git checkout/git subodule update
    # cd esp-idf
    # ./install.sh esp32s3
    # source export.sh
# To generate micropython  image:
# For a certain version add: --branch v1.28.0
    # git clone --depth 1 https://github.com/micropython/micropython.git
    # Adjust folders in this program, then run fix_mp_romfs.py
    # Running that program will
    #to add partitions file and define necessary compilation flags. 
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
    # No spaces allowed in FROZEN_MANIFEST path (even if enclosed in "")
    # Create a soft link:
    # ln -s "/Users/username/some folder/another folder/crank-organ/tools/" crank_organ_tools
    #
    # Compile micropython:
    # % cd micropython/ports/esp32
	# % rm -f -r build-ESP32_GENER* folders
	# % make clean
	# % make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT submodules
	# % make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT FROZEN_MANIFEST=/Users/username/make BOARD=ESP32_GENERIC_S3 BOARD_VARIANT=SPIRAM_OCT FROZEN_MANIFEST=/Users/username/crank_organ_tools/manifest.py
    # The output are the .bin files
    # .bin files are now in micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT folder
    # Copy to bin folder with 
    # % gmake copy_mp_bin

from pathlib import Path
from shutil import copy
import os

home_path = Path.home()
port_path = home_path / "micropython/ports/esp32"
my_path = Path(__file__).parent
modules_path = port_path / "modules"

board_path = port_path / "boards/ESP32_GENERIC_S3"
print(f"{home_path=}")
print(f"{port_path=}")
print(f"{my_path=}")
PARTITION_FILENAME = "partitions-4MiB-BIG-romfs.csv"

def add_partition_csv():
    partition_dst = port_path / PARTITION_FILENAME
    copy( my_path / PARTITION_FILENAME, partition_dst )
    print(partition_dst.name, "copied as new partition file")

def fix_sdkconfig_board():
    sdkconfig_filename = board_path / "sdkconfig.board"
    with open( sdkconfig_filename ) as input:
        sdkconfig = input.read()

    if "CONFIG_PARTITION_TABLE_CUSTOM" in sdkconfig:
        print(f"{sdkconfig_filename.name} already has custom ROMFS partition defined")
        return
    sdkconfig += "\nCONFIG_PARTITION_TABLE_CUSTOM=y\n"
    sdkconfig += f'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="{PARTITION_FILENAME}"\n'
    with open( sdkconfig_filename, "w") as output:
        output.write( sdkconfig )
    print(f"{sdkconfig_filename} added custom ROMFS partition")

def fix_mpconfigboard():
    def add_define( define, value ):
        nonlocal mpconfigport, dirty
        define_line = f"#define {define} ({value})"
        if define_line in mpconfigport:
            
            print( f"{mpconfig_filename.name} already has {define} defined as {value}")
        else:
            dirty = True
            mpconfigport += "\n"
            mpconfigport += "#ifdef " + define + "\n"
            mpconfigport += "#undef "+ define + "\n"
            mpconfigport += "#endif\n"
            mpconfigport += define_line + "\n"
            print(f"{mpconfig_filename} added {define} defined as {value}")
    
    def remove_module( module_name ):
        module_path = board_path / "modules"
        frozen_path = board_path / "build-ESP32_GENERIC_S3-SPIRAM_OCT" / "frozen_mpy"
        try:
            os.remove( module_path / (module_name+".py") )
            print(f"{module_name} removed from {module_path}")
            os.remove( frozen_path / (module_name+".mpy") )
            print(f"{module_name} .mpy removed from {frozen_path}")
        except OSError:
            print(f"{module_name} not found in {module_path}, no need to remove")


    mpconfig_filename = board_path / "mpconfigboard.h"
    with open(mpconfig_filename ) as input:
        mpconfigport = input.read()
    dirty = False
    add_define( "MICROPY_VFS_ROM", 1 )

    # Disable features to reduce MicroPython's size in bin image
    add_define( "MICROPY_PY_APA106", 0) #
    remove_module( "apa106" ) # remove apa105.py
    add_define( "MICROPY_PY_BTREE", 0)
    add_define( "MICROPY_PY_ESPNOW", 0) # remove _espnow
    remove_module( "espnow" ) # remove espnow.py too
    add_define( "MICROPY_PY_HEAPQ", 0 )
    add_define( "MICROPY_PY_FRAMEBUF", 0)
    # >>> Still can  remove: requests, webrepl, onewire, thread, 
    # See https://github.com/orgs/micropython/discussions/12303 for repl, webrepl
    # #define MICROPY_ENABLE_COMPILER (0)
    # will disable repl and make more difficult to inject code.
    
    if dirty:
        with open( mpconfig_filename, "w" ) as output:
            output.write( mpconfigport )
        print(f"{mpconfig_filename} updated")
    else:
        print(f"{mpconfig_filename.name} no need to update.")

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

# April 2026 romfs size:
# Image size is 236886 bytes
# ROMFS0 partition has size 262144 bytes (64 blocks of 4096 bytes each)
# Writing 236870 bytes to output file crank-organ/bin/romfs.bin
# 25285 bytes still free.