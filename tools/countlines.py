# Utility to count lines
import os
import os.path # type:ignore

py_folder = "crank-organ/src" 
static_folder = "crank-organ/static"
data_folder = "crank-organ/data"
mpy_folder = "device/mpy"
static_folder_gz = "device/static"


#py_folder = "github-clone/crank-organ/src" 
#mpy_folder = ""
#static_folder = ""


def isexcept( fn ):
    return fn in ["mcp23017.py", "uftpd.py", "microdot.py" ]
    #return False

def countlines( fn, filelist ):
    lines = 0
    comments = 0
    try:
        with open(fn, "r") as file:
            while True:
                line = file.readline()
                if not line:
                    break
                line = line.replace("\t","")
                line = line.replace("\n", "")
                line = line.replace(" ", "")
                line = line.strip()
                if line == "":
                    continue
                if line[0:1] != "#":
                    if line:
                        lines += 1
                else:
                    comments += 1

        filelist.append(( fn, lines, comments ))
    except IsADirectoryError:
        print("skip file", fn )
    return 

def countlines_html( fn, filelist ):
    lines = 0
    comments = 0
    count = False
    if fn.endswith(".js"):
        count = True
    try:
        with open(fn, "r") as file:
            while True:
                line = file.readline()
                if not line:
                    break
                if "<script>" in line:
                    count = True
                if "<script/>" in line:
                    count = False
                if not count:
                    continue
                line = line.replace("\t","")
                line = line.replace("\n", "")
                line = line.replace(" ", "")
                line = line.strip()
                if line == "" or len(line) == 1:
                    continue
                if line[0:2] != "//":
                    if line:
                        lines += 1
                else:
                    comments += 1

        filelist.append(( fn, lines, comments ))
    except IsADirectoryError:
        print("skip file", fn )
    return 


def count_size():

    n = 0
    py_bytes = 0
    filelist = []
    for fn in os.listdir(py_folder):
        if fn[-3:] == ".py" and not isexcept(fn):
            filename = os.path.join( py_folder, fn )
            countlines( filename, filelist )
            py_bytes += os.stat( filename ).st_size
            n += 1
    filelist.sort( key=lambda x : -x[1] )
    for fn, lines, comments in filelist:
        print(f"{fn:40s} {lines:4d} lines {comments/(lines+comments)*100:2.0f}% comments")

    total = sum ( x for _,x,_ in filelist )
    print(f"Total {n} files {total} lines {py_bytes:_} bytes")
    print("")

    print("Common libraries")
    n = 0
    filelist = []
    for fn in os.listdir(py_folder):
        if fn[-3:] == ".py" and isexcept(fn):
            countlines(  os.path.join( py_folder, fn ), filelist )
            n += 1
    filelist.sort( key=lambda x : -x[1] )
    for fn, lines, comments in filelist:
        print(f"{fn:40s} {lines:4d} lines {comments/(lines+comments)*100:2.0f}% comments")

    total = sum ( x for _,x,_ in filelist )
    print(f"Total {n} files {total} lines")
    print("")
    
    print("HTML files")
    n = 0
    js_lines = 0
    filelist = []
    for fn in os.listdir(static_folder):
        if fn[-5:] == ".html" or fn[-3:] == ".js":
            countlines_html(  os.path.join( static_folder, fn ), filelist )
            n += 1
    filelist.sort( key=lambda x : -x[1] )
    for fn, lines, comments in filelist:
        print(f"{fn:40s} {lines:4d} lines {comments/(lines+comments)*100:2.0f}% comments")
    total = sum ( x for _,x,_ in filelist )
    print(f"Total {n} files {total} lines")
    print("")
        
    if mpy_folder:
        sum_mpy = 0
        n = 0
        for fn in os.listdir(mpy_folder):
            if fn.endswith(".mpy"):
                sum_mpy += os.stat( os.path.join( mpy_folder, fn )).st_size
                n += 1
        print(f"Total {n} mpy files {sum_mpy:_} bytes")

    if static_folder_gz:
        sum_static = 0
        n = 0
        for fn in os.listdir(static_folder_gz):
            sum_static += os.stat( os.path.join( static_folder_gz, fn )).st_size
            n += 1
        print(f"Total {n} compressed files in static folder {sum_static:_} bytes")


def count_blocks():
    blocks = {}
    for folder in [py_folder, static_folder, data_folder, mpy_folder, static_folder_gz]:
        blocks[folder] = 0
        for fn in os.listdir(folder):
            filename = folder + "/" + fn
            size = os.stat(filename).st_size
            blocks[folder]  += (size+4095)//4096
        print(folder, blocks[folder], "blocks")
    # Folder /data approx 120 blocks
    compressed = 512 + 120 + blocks[mpy_folder] + blocks[static_folder_gz]
    uncompressed = 512 + 120 + blocks[py_folder] + blocks[static_folder]
    print(f"Compressed {compressed} blocks, uncompressed {uncompressed} blocks including MicroPython")

count_size()
count_blocks()
