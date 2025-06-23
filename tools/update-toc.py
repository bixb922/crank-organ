# Utility to generate automatic table of contents for .md markdown files
 
import sys
import re
import os

level0 = 0

def get_link( line ):
    line = line.strip().lower()
    for c in ".,":
        line = line.replace(c, "")
    for c in line:
        if c not in "abcdefghijklmnopqrstuvwxyz0123456789":
            line = line.replace(c, "-")
    while line[-1:] == "-":
        line = line[0:-1]
    while line[0:1] == "-":
        line = line[1:]
    while "--" in line:
        line = line.replace("--", "-")
    return line

def process_header( line, output, toc ):
    global level0
    n = 0
    while n < len(line) and line[n:n+1] == "#":
        n += 1
    line = line.strip()
    if n == 1:
        level0 += 1
        if level0 < 0 or "# Contents" in line:
            # Skip first # and contents for numbering
            output.append( line )
            if "# Contents" in line:
                level0 = 0
            return
        pattern = "#[ 0-9]+(.*)$"
        m = re.match(pattern, line)
        if not m:
            print(line)
            raise RuntimeError(f"Incorrect format for header line, does not match {pattern}")
        numbering = str(level0) + ". "
        header = numbering + m.group(1)
        link = get_link( header )
        print("    toc", f"{numbering} [{m.group(1)}](#{link})")
        toc.append( f"{numbering} [{m.group(1)}](#{link})" )
        output.append( "# " + header )
    else:
        link = get_link(line[n:])
        prefix = ' '*((n-1)*4)
        toc.append( f"{prefix} * [{line[n:].strip()}](#{link})" )
        output.append( line )

def process( filename ):
    toc = []
    output = []
    content_start = None
    content_end = None
    line_number = -1
    with open( filename ) as file:
        while True:
            line = file.readline()
            line_number += 1
            if not line:
                break
            if len(line) >= 1 and line[0:1] == "#":
                process_header( line, output, toc )
                if line.strip() == "# Contents":
                    content_start = line_number+1
                elif line.strip()[0:1] == "#" and not content_end:
                    content_end = line_number
            else:
                output.append(line[0:-1])
    if content_start and content_end:
        print("    replacing contents from line", content_start, "to", content_end )
        output[content_start:content_end] = toc
    else:
        print("    ?No '# Contents' found")
    return output


def main():
    global level0
    files = [   "crank-organ/doc-hardware/crank-sensor.md", 
                "crank-organ/doc-hardware/README.md",
                "crank-organ/doc-software/README.md",
                "crank-organ/doc-hardware/battery.md",
                 "crank-organ/doc-hardware/servos.md",
                "crank-organ/README.md",
			 	"crank-organ/building/README.md",
                "crank-organ/design_and_development/design_and_development.md"]
    for output_filename in files:
        input_filename = output_filename.replace(".md", "_editable.md")
        print("Processing", input_filename )
        level0 = -2
        output = process( input_filename )
        with open(output_filename, "w") as file:
            for line in output:
                if line[-1:] != "\n":
                    line += "\n"
                file.write( line)
        print("    ", output_filename, "written")
main()