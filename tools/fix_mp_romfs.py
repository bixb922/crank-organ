# Fix MicroPython .bin image generation for romfs
# This enables generate a custom board version for
# new versions of MicroPython. Just "git clone" the new version
# and run this program to make all needed changes.
# MicroPython version >= v1.28
# Get esp-idf, see: https://github.com/micropython/micropython/tree/master/ports/esp32
    # git clone ...
    # (needs about 3.3Gb)
    # no need for git checkout/git subodule update
    # cd esp-idf
    # ./install.sh esp32s3
    # source export.sh
# To generate micropython  image:
    # git clone --branch v1.28.0 --depth 1 https://github.com/micropython/micropython.git
    #   (needs about 45Mb)
    # Adjust folders in this program to your PC, then run this program.
    # Running that program will add partitions file and define necessary compilation flags. 
    
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
    # No spaces allowed in FROZEN_MANIFEST path (even if enclosed in "")
    # Create a soft link to this folder for the FROZEN_MANIFEST path:
    # ln -s "/Users/username/some folder/another folder/crank-organ/tools/" crank_organ_tools
    #
    # To compile MicroPython see commands printed at end of main()

    # The output are three .bin files to be found in
    # micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT folder
    # Copy to bin folder with 
    # % gmake copy_mp_bin
    # or use with esptool.py. See .sh files in crank-organ/bin folder
    # for appropriate esptool command.

from pathlib import Path
from shutil import copy, rmtree, copytree
import re

home_path = Path.home()
port_path = home_path / "micropython/ports/esp32"
crank_organ_tools_path = Path(__file__).parent
modules_path = port_path / "modules"

base_board_name = "ESP32_GENERIC_S3"
base_board_path = port_path / "boards" / base_board_name
custom_board_name = "ESP32_MUSICAL_S3"
custom_board_path =  port_path / "boards"/ custom_board_name

print(f"{home_path=}")
print(f"{port_path=}")
print(f"{crank_organ_tools_path=}")
print(f"{base_board_path=}")
print(f"{custom_board_path=}")
print("")

PARTITION_FILENAME = "partitions-4MiB-BIG-romfs.csv"
partition_destination_path = custom_board_path / PARTITION_FILENAME 
partition_relative_path = f"boards/{custom_board_name}/{PARTITION_FILENAME}"

mpconfigvariant_filename = custom_board_path /  "mpconfigvariant_SPIRAM_OCT.cmake"

def read_file( filename ):
    with open(filename) as file:
        return file.read()
    
def write_file( filename, new_contents ):
    with open(filename,"w") as file:
        file.write( new_contents )

def replace( filename, pattern, repl ):
    data = read_file( filename )
    match = re.search( pattern, data, flags=re.MULTILINE  )
    if not match:
        print(f"???filename.name: {pattern} not matched")
        return
    span = match.span()
    new_data = data[0:span[0]] + repl + data[span[1]:]
    if new_data != data:
        print(f"{filename.name}: pattern '{pattern}' changed to '{repl}'")
        write_file( filename, new_data )
    else:
        print(f"{filename.name}: pattern '{pattern}' no need to rewrite file, already changed")

def append( filename, to_be_appended ):
    data = read_file( filename )
    write_file( filename, data + "\n"+ to_be_appended)
    

def fill_new_board_folder():
    try:
        rmtree( custom_board_path )
        print("Custom board folder emptied")
    except FileNotFoundError:
        print("Custom board path not found, creating new custom board folder")
    copytree( base_board_path, custom_board_path )
    print(f"{base_board_name}: board definition copied to custom board folder {custom_board_name}")


def add_partition_csv():
    copy( crank_organ_tools_path / PARTITION_FILENAME, partition_destination_path )
    print( f"{PARTITION_FILENAME}: copied as a new partition file")
    return

def fix_sdkconfig_board():
    sdkconfig_filename = custom_board_path / "sdkconfig.board"
    append( sdkconfig_filename, 
        "\nCONFIG_PARTITION_TABLE_CUSTOM=y\n"+
        f'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="{partition_relative_path}"\n'
    )
    
    print(f"{sdkconfig_filename.name}: defined custom ROMFS partition")

def add_define( mpconfigport, define, value ):
    mpconfigport += "\n"
    mpconfigport += "#ifdef " + define + "\n"
    mpconfigport += "#undef "+ define + "\n"
    mpconfigport += "#endif\n"
    mpconfigport += f"#define {define} ({value})\n"
    return mpconfigport
    
def fix_mpconfigboard():
    defines = {
        "MICROPY_VFS_ROM": 1,
        "MICROPY_PY_BTREE": 0,
        "MICROPY_PY_HEAPQ": 0,
        "MICROPY_PY_FRAMEBUF": 0,
        "MICROPY_HW_ENABLE_SDCARD":0,
        "MICROPY_VFS_FAT":0,
        # "MICROPY_PY_DEFLATE_COMPRESS": 1,
        }
     
    mpconfig_filename = custom_board_path / "mpconfigboard.h"

    mpconfigport = read_file( mpconfig_filename )
    mpconfigport.replace("Generic ESP32S3 module", "Musical ESP32S3 module")

    # Disable features to reduce MicroPython's size in bin image
    # Enable ROMFS.
    for name, value in defines.items():
        mpconfigport = add_define( mpconfigport, name, value )
        print(f"{mpconfig_filename.name}: added {name} defined as {value}")
    
    # Also see bundle-networking in tools/manifest.py
    # See https://github.com/orgs/micropython/discussions/12303 for repl, webrepl
    # See "Securing a MicroPython system" on MicroPython wiki
    # "MICROPY_ENABLE_COMPILER": 0
    # "MICROPY_HW_ENABLE_UART_REPL": 0
    
    write_file( mpconfig_filename, mpconfigport )
  
    print(f"{mpconfig_filename.name} updated")

def fix_cmake():
    cmake_filename = custom_board_path / "mpconfigboard.cmake"
    replace( cmake_filename,
            base_board_name,
            custom_board_name )
    print(f"{cmake_filename.name}: updated path for sdkconfig.base")

def change_board_name():
    replace( mpconfigvariant_filename,
            "Generic ESP32S3 module with Octal-SPIRAM",
            "Musical ESP32S3 module with Octal-SPIRAM"
            )
    print("Board name changed")

def patch_mpconfigport():
    mpconfigport_filename = port_path / "mpconfigport.h"
    replace( mpconfigport_filename, 
            r"#define MICROPY_PY_WEBSOCKET\s+(.+)",
            "#define MICROPY_PY_WEBSOCKET (0)")

    replace( mpconfigport_filename, 
            r"#define MICROPY_PY_WEBREPL\s+(.+)",
            "#define MICROPY_PY_WEBREPL (0)")
    
# >>> for webrepl also modify these:
# https://github.com/orgs/micropython/discussions/12303
# micropython/extmod/extmod.cmake
#  diff extmod.cmake extmod.cmake-ORIG
# 39a40
# >     ${MICROPY_EXTMOD_DIR}/modwebrepl.c
#
# micropython/extmod/extmod.mk"
# $ diff extmod.mk extmod.mk-ORIG
# 36a37
# > 	extmod/modwebrepl.c \

    replace( mpconfigport_filename, 
            r"#define MICROPY_PY_ONEWIRE\s+(.+)",
            "#define MICROPY_PY_ONEWIRE (0)")

 
def update_romfs_start_addr():
    print("Update ROMFS start address in docs and shell files")
    partition = read_file( crank_organ_tools_path / PARTITION_FILENAME )
    # romfs,    data, 0x8f,    0x1B0000,   0x50000
    match = re.search( f"romfs.*0x(1[a-fA-F0-9]+),", partition, re.MULTILINE )
    if match:
        romfs_addr = match.group(1)
        print(f"{PARTITION_FILENAME}: found ROMFS address 0x{romfs_addr}")
    else:
        print(f"???{PARTITION_FILENAME}: no ROMFS address found" )
        return
    
    docs_path = crank_organ_tools_path.parent / "doc-software"
    docs_file =  docs_path / "README_editable.md"
    # Use a very specific pattern to avoid the span be too large
    replace( docs_file,
            r"micropython\.bin\s+0x[a-zA-Z0-9]+\s+romfs\.bin", 
            f"micropython.bin 0x{romfs_addr} romfs.bin" )
    
    bin_path = crank_organ_tools_path.parent / "bin"
    replace( bin_path / "full_flash.sh", 
            r"micropython\.bin.+romfs\.bin", 
            f"micropython.bin 0x{romfs_addr} romfs.bin" )
    replace( bin_path / "romfs_flash.sh", 
            r"80m.+romfs\.bin", 
            f"80m 0x{romfs_addr} romfs.bin" )

def main():
    fill_new_board_folder()
    add_partition_csv()
    fix_sdkconfig_board()
    fix_mpconfigboard()
    fix_cmake()
    change_board_name()
    patch_mpconfigport()
    update_romfs_start_addr()


    print("")
    print("Commands to generate MicroPython, copy and paste:")
    print(f"make BOARD={custom_board_name} BOARD_VARIANT=SPIRAM_OCT submodules")
    print(f"make clean BOARD={custom_board_name} BOARD_VARIANT=SPIRAM_OCT")
    username = crank_organ_tools_path.parts[2] 
    print(f"make BOARD={custom_board_name} BOARD_VARIANT=SPIRAM_OCT FROZEN_MANIFEST=/Users/{username}/crank_organ_tools/manifest.py")

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

# May 2026, romfs, 20_note_Carl_Frei.json
# Total startup time (without main, until asyncio ready) 1262 msec
# Memory used at startup 126464 gc=19 msec
# 
# Number of note influences startup time and memory usage.
# Per note or pin memory used at startup increases about 500 bytes
# for all the datastructures kept to make note on/off fast.

# May 2026 MicroPython sizes, no ROMFS, no define 0 added, small manifest.py
# bootloader  @0x000000    19232  (   13536 remaining)
# partitions  @0x008000     3072  (    1024 remaining)
# application @0x010000  1682528  (  349088 remaining)
# total                  1748064

# May 2026, ROMFS added, define 0 added, small manifest
# micropython.bin binary size 0x194410 bytes. Smallest app partition is 0x1a8000 bytes. 0x13bf0 bytes (5%) free.
# Warning: The smallest app partition is nearly full (5% free space left)!# bootloader  @0x000000    19232  (   13536 remaining)
# partitions  @0x008000     3072  (    1024 remaining)
# application @0x010000  1655824  (   80880 remaining)
# total                  1721360
# romfs.bin =  243958 bytes/0x48000 = 82% = 51.000 bytes free 
# MicroPython = 0x194410 bytes/0x1A8000 = 95.3% = 81.000 bytes free

# MicroPython generated with no SD card, no FAT, no websocket, webrepl, onewire
# micropython.bin binary size 0x186640 bytes. Smallest app partition is 0x1a8000 bytes. 0x219c0 bytes (8%) free.
# bootloader  @0x000000    19232  (   13536 remaining)
# partitions  @0x008000     3072  (    1024 remaining)
# application @0x010000  1599040  (  137664 remaining)
# total                  1664576
# MicroPython = 0x186640/0x1A8000= 92% = 137664 free
# ROMFS = 243770 = 0x3b83a/0x50000 = 74% = 84190 free

# July 2026, after adding tarfile and tarfile-write modules
#   1602656 Jun 30 23:51 micropython.bin
#    246694 Jul  1 00:09 romfs.bin
# MicroPython = 1602656/0x1A8000= 92% = 101280 free
# ROMFS = 247402 = 247402/0x50000 = 76% = 80278 free
#
# July 2026, 20 note Carl Frei pinout.json, 600 midi files
# Total startup time (without main, until asyncio ready) 1995 msec
#   Memory used at startup 126656 gc=21 msec