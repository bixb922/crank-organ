import os
# Mount file system with more appropriate file system parameters:
# lookahead must increase to make space for the size of the flash.
# Optimal value of lookahead is the (number of blocks of the flash)/8
# since then the complete bitmap of free blocks is in RAM.
# Overhead setting to a large value is low.
# 16Mb = 4096 blocks/8 bits per byte=512 bytes for lookahead size, 
# although it could be a bit lower since 
# not all 16 MB are really available.
# Largest impact is readsize=. Impact of lookahead= is low.
# Mount is done in boot.py, since that speeds up mpremote too,

os.umount("/")
# This makes the file system much faster, especially if there are many files
os.mount(os.VfsLfs2(bdev, readsize=4096, progsize=128, lookahead=512), "/") # type:ignore
print("boot.py mount readsize=4096, progsize=128, lookahead=512")

# Copy main.py from /rom to root, but only if not already copied.
# Must be main.py, since a compiled main.mpy is ignored.
# If main.py should not execute, copy an empty file as main.py to
# the root of the microcontroller.
try:
    # Test if main.py is there
    open("main.py").close()
except OSError:
    # main.py not in root. Copy from romfs (if installed) to root.
    try:
        with open("/rom/main.py") as input:
            with open("/main.py", "w") as output:
                output.write( input.read() )
        print("main.py copied from /rom/main.py to /main.py")
    except OSError:
        pass


