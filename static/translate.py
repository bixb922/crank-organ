# translate --language=english input.html output.html
#

import os
import sys

def read_dictionary(language):
    # Read the translation dictionary, one entry for each file
    # Translation file is in the same folder as this .py
    translation_file = os.path.join( os.path.dirname(__file__), language + ".dictionary")
    dictionary = {}
    with open(translation_file, "r",  encoding="utf-8") as file:
        while True:
            s = file.readline()
            if s == "":
                break
            # Ignore blank and comment lines
            if s == "\n" or s[0:1] == "#":
                continue
            s = s.replace("\n", "")
            if s[0:1] == "*":
                # Store filename
                input_filename =  s[1:]
                dictionary[input_filename] = []
            else:
                pair = s.split("|")
                if len(pair) != 2:
                    print("???bad translation format, no | or more than one found:", s)
                    sys.exit(1)
                else:
                    # Dictionary entry is from-word, to-word and use counter
                    dictionary[input_filename].append( [pair[0], pair[1], 0 ] )
    return dictionary

def translate_file( language, input_filename, output_filename ):
    dictionary = read_dictionary(language)

    base_name = os.path.basename( input_filename )
    if base_name not in dictionary:
        print(f"???Input filename {base_name} not in dictionary")
        sys.exit(1)
        
    translate_with = dictionary[base_name]
    
    print("Processing file", input_filename, "->", output_filename)
    with open( input_filename, "r",  encoding="utf-8") as file:
        input_string = file.read()
        
    output_string = input_string
    for i, (from_string, to_string, count) in enumerate(translate_with):
        if from_string in output_string and count == 0:
            # Translate and count use of rule
            translate_with[i][2] += 1
            output_string = output_string.replace( from_string, to_string )
    with open( output_filename, "w", encoding="utf-8") as file:
        file.write( output_string )
            
    # Check each rule was used
    for i, (from_string, to_string, count) in enumerate(translate_with):
        if count == 0:
            print( input_filename, "rule", from_string, to_string, "not used")
            sys.exit(1)
        

def main():
    args = sys.argv[1:]
    if len(args) != 3:
        print("???Must have 3 command line arguments: language input-file output-file")
        sys.exit(1)
    if args[0] not in ["english", "spanish"]:
        print("???First argument must be language: english, spanish")
        sys.exit(1)
        
    language = args[0]
    input_file = args[1]
    output_file = args[2]
    if language == "spanish":
            with open( input_file) as file:
                    s = file.read()
            with open( output_file, "w") as file:
                    file.write(s)
            sys.exit(0);
    translate_file( language, input_file, output_file )
    
main()
