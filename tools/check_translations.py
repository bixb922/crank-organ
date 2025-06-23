# This is a tool used during development to check
# consistency of the translations (translations.js)
from html.parser import HTMLParser
import os

do_not_translate = ["", "\xa0", "\xa0\xa0","\xa0\xa0\xa0",
    "⬅", " Home page", "Server link", "🔧", "🎛","📚",
     "📆","🎨","🎨","🔍","FTP","📂","[hh:mm]","1️⃣","2️⃣",
     "⏪ "," ⏩","nnn",",","Host name","(","Reset", "Deep sleep",
     "[bytes]","Host name, AP SSID, BLE name:",
     "IP", "Connection status","SSID","IP","WiFi scan",
     "SSID","dBm","Cents","Pin","👑", "🎼🎵🎶", "..."]
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
        stripped_data = data.strip(" \n\r\t")
        if stripped_data in do_not_translate:
            return
        if self.tag == "script":
            check_script( data, self.translations, self.pagename, self.tag, self.translations_used )
            return 
        text = stripped_data.lower()
        if text not in self.translations:
            print(f"not found page {self.pagename} tag <{self.tag}> data='{stripped_data}'")
        else:
            self.translations_used.append( text )

def check_script( script, translations, pagename, tag, translations_used ):
    if "ttl(" in script:
        print("Error, there is a ttl() in script!")
    while "tlt(" in script:
        p = script.index("tlt(")
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
            print(f"script tlt not found page {pagename} tag <{tag}> data='{tlt_text}'")
        else:
            translations_used.append( tlt_text )

def read_translations():
    t = {}
    with open("translations.js") as file:
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
                # "key": // some stuff
                key = line.split('"')[1]
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
    translations = read_translations()
    translations_used = []
    filelist = os.listdir()
    folder = "../../server/mysite/iot/static/"
    filelist.extend( [folder + fn for fn in os.listdir( folder )])
    for filename in filelist:
        if not filename.endswith(".html"):
            continue
        pagename = filename.replace("/",".").split( ".")[-2]
        with open(filename) as file:
            data = file.read()
        there_is_translations_js = "translations.js" in data
        there_is_translate_html = "translate_html()" in data
        if there_is_translate_html != there_is_translations_js:
            print(f"Error in {filename}: either translations.js ({there_is_translations_js}) or translate_html() ({there_is_translate_html}) is missing")
            continue
        if not there_is_translations_js and not there_is_translate_html:
            print("File skipped: ", filename )
            continue
        print("checking", filename, "...")
        parser = MyHTMLParser(pagename, translations)
        parser.feed(data)
        translations_used.extend( parser.translations_used)
    with open("common.js") as file:
        check_script( file.read(), translations, "common.js", "-", translations_used )

    print("Check for unused translations...")
    for k in translations.keys():
        if k not in translations_used:
            print("unused translation", k)
main()
