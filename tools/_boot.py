# _boot.py for .bin image with ROMFS
# This _boot.py will copy main.py from ROMFS to flash
# so the system on the ROMFS will boot.
import gc
import vfs
from flashbdev import bdev

try:
    if bdev:
        vfs.mount(bdev, "/")
except OSError:
    import inisetup

    inisetup.setup()

# Copy main.py from /rom to root, but only if not already there
# Must be main.py, a compiled main.mpy is ignored.
try:
    open("main.py").close()
except OSError:
    try:
        with open("/rom/main.py") as input:
            with open("/main.py", "w") as output:
                output.write( input.read() )
        print("main.py copied from /rom/main.py to /main.py")
    except OSError:
        pass
gc.collect()


