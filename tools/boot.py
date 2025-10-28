import os
os.umount("/")
# This makes the file system much faster, especially if there are many files
os.mount(os.VfsLfs2(bdev, readsize=4096, progsize=128, lookahead=512), "/") # type:ignore
print("boot.py mount readsize=4096, progsize=128, lookahead=512")

# Copy main.py from /rom to root, but only if not already there
# Must be main.py, a compiled main.mpy is ignored.
try:
    # Test if main.py is there
    open("main.py").close()
except OSError:
    # Not there, copy from romfs (if installed) to root.
    try:
        with open("/rom/main.py") as input:
            with open("/main.py", "w") as output:
                output.write( input.read() )
        print("main.py copied from /rom/main.py to /main.py")
    except OSError:
        pass


