# (c) Copyright 2025 Hermann Paul von Borries. All rights reserved.
# MIT License

# This is a tool used during development to check
# consistency of the translations (translations.js)
from html.parser import HTMLParser
import os, sys
errors_found = 0

do_not_translate = ["", "\xa0", "\xa0\xa0","\xa0\xa0\xa0",
    "⬅", " Home page", "Server link", "🔧", "🎛","📚",
     "📆","🎨","🎨","🔍","FTP","📂","[hh:mm]","1️⃣","2️⃣",
     "⏪ "," ⏩","nnn",",","Host name","(","Reset", "Deep sleep",
     "[bytes]","Host name, AP SSID, BLE name:",
     "IP", "Connection status","SSID","IP","WiFi scan",
     "SSID","dBm","Cents","Pin","👑", "🎼🎵🎶", "...", "×"]
class MyHTMLParser(HTMLParser):
    def __init__(self, pagename, translations):
        self.pagename = pagename
        self.translations = translations
        self.tag = ""
        self.translations_used = []
        super().__init__()

    def handle_starttag(self, tag, attrs):
        self.tag = tag

    def handle_endtag(self, tag):
        self.tag = "/" + tag

    def handle_data(self, data):
        global errors_found
        stripped_data = data.strip(" \n\r\t")
        if stripped_data in do_not_translate:
            return
        if self.tag == "script":
            check_script( data, self.translations, self.pagename, self.tag, self.translations_used )
            return 
        text = stripped_data.lower()
        if text not in self.translations and not stripped_data.startswith("© Copyright"):
            print(f"    not found page {self.pagename} tag <{self.tag}> data='{stripped_data}'")
            errors_found +=1
        else:
            self.translations_used.append( text )

def check_script( script, translations, pagename, tag, translations_used ):
    global errors_found
    if "ttl(" in script:
        print("    Error, there is a ttl() instead of tlt() in script!")
        errors_found += 1
    # common.js has "function tlt", skip that, also skip use
    # of tlt inside translate_html()
    if "function tlt" in script:
        p = script.index("function tlt")
        script = script[0:p-1] + script[p+13:]
    if "tlt(d.innerText)" in script:
        p = script.index("tlt(d.innerText)")
        script = script[0:p-1] + script[p+20:]

    while "tlt(" in script:
        p = script.index("tlt(")
        if script[p+4:p+5] != '"' and script[p+5:p+6] != '"':
            print( "    Error, tlt() does not translate literal:", script[p:p+20])
            errors_found += 1
        while script[p] != '"':
            p = p + 1
            assert p < len(script)
        p = p + 1
        q = p
        while script[q] != '"':
            q = q + 1
        tlt_text = script[p:q].lower()
        script = script[q:]
        if tlt_text not in translations:
            print(f"    tlt() in javascript not found page {pagename} tag <{tag}> data='{tlt_text}'")
            errors_found += 1
        else:
            translations_used.append( tlt_text )

def read_translations(filename):
    global errors_found
    print("Reading translations from", filename)
    t = {}
    with open(filename) as file:
        copy = False
        while True:
            line = file.readline()
            if not line:
                break
            if line.startswith("let translationDict"):
                copy = True
                continue
            if not copy:
                continue
            line = line.strip(" \n\t")
            if line.startswith("}"):
                # end of translationDict
                break
            if line.startswith("//") or line == "":
                # skip comments and blank lines
                continue
            # Process dict key and translation lines
            if line[0] == '"' and ":" in line:
                # "key": // page where it occurs
                key = line.split('"')[1]
                if key != key.lower():
                    print(f"    Must be lower case: {key}")
                    errors_found += 1
            elif line[0] == "[":
                # ["one language", "other language"],
                tr = line.split(",")
                for i in range(len(tr)):
                    s = tr[i].strip("[], ")
                    s = s.strip('"')
                    tr[i] = s
                t[key] = tr
    return t

def main():
    filelist = []
    for folder in [ "crank-organ/static/", "server/mysite/iot/static/"]:
        filelist.extend( [folder + fn for fn in os.listdir(folder) if fn.endswith(".html")] )
    analyze_translations(folder, filelist)
    print("")
    if errors_found:
        print("?Errors found in check translations")
        sys.exit(1)


def analyze_translations(folder, filelist):
    global errors_found
    translations = read_translations(folder + "translations.js")
    translations_used = []
    for filename in filelist:
        if not filename.endswith(".html"):
            continue
        pagename = filename.replace("/",".").split( ".")[-2]
        with open(filename) as file:
            data = file.read()
        there_is_translations_js = "translations.js" in data
        there_is_translate_html = "translate_html()" in data
        if not there_is_translations_js:
            print(f"Error in {filename}: translations.js is missing")
            errors_found += 1
            continue
        if not there_is_translate_html:
            print("File skipped, no translations: ", filename )
            continue
        print("Checking:                      ", filename )
        parser = MyHTMLParser(pagename, translations)
        parser.feed(data)
        translations_used.extend( parser.translations_used)

    with open(folder + "common.js") as file:
        print("Checking:                       crank-organ/static/common.js")
        check_script( file.read(), translations, "common.js", "-", translations_used )

    print("Check for unused translations:")
    unused = False
    for k in translations.keys():
        if k not in translations_used:
            print("Unused translation", k)
            unused = True
    if not unused:
        print("    No unused translations")

main()
