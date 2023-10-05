
import os
import sys
import gc
import asyncio
import json
import time

import tinyweb
from minilog import getLogger
import scheduler
import config
import pinout
import battery
import wifimanager
import solenoid
import modes
from tinytz import ttz

# Allowed pages for each mode
_ALLOWED_PAGES = {
"play": ("index.html","diag.html", "play.html", "tunelist.html", "config.html"),
"tuner": ("index.html", "diag.html", "note.html", "notelist.html", "config.html" ),
"keyboard": ("index.html", "diag.html", "keyboard.html", "config.html"),
"config": {"index.html", "pinout.html", "config.html"}
} 

app = tinyweb.webserver( debug=True )
FILE_BUF_SIZE = None # will be changed by run_webserver()
USE_CACHE = True # will be set by run_webserver() to value in config.json
MAX_AGE = 24*60*60 # Pages are in cache for 1 day. Will be set to 0 of no cache
_pages_served = 0

def _file_exists( filename ):
    try:
        os.stat( filename )
        return True
    except:
        return False

    
def set_mode():
    if modes.is_play_mode():
        global tunelist, tachometer, player, setlist
        import tunelist
        import tachometer
        import player
        import setlist
    elif modes.is_tuner_mode():
        global organtuner
        import organtuner
    elif modes.is_keyboard_mode():
        global soleble
        import soleble

set_mode()

# Information active clients
# key=client IP, data=time.ticks_ms()) of last activity
client_activity = {}
def register_activity( request ):
    client_activity[request.caddr[0]] = time.ticks_ms()


def is_active( since_seconds=60 ):
    # This is used by poweroff.py
    try:
        t =  time.ticks_diff( time.ticks_ms(),
                             min( list( client_activity.values() ) ) )
        # Return true if recent activity
        return t < since_seconds*1000 
    except ValueError:
		# no client activity, empty list 
            pass
    return False


_CONTENT_TYPE_DICT = {
        "gif": "image/gif",
        "ico": "image/x-icon",
        "png": "image/png",
        "css": "text/css; charset=UTF-8",
        "htm": "text/html; charset=UTF-8",
        "html": "text/html; charset=UTF-8",
        "js":  "application/javascript; charset=UTF-8",
        "json": "application/json; charset=UTF-8",
        "tsv": "text/tab-separated-values; charset=UTF-8",
        "log": "text/html; charset=UTF-8"
    }

def get_content_type( filename ):
    try:
        filetype = filename.split(".")[1].lower()
        if filetype in _CONTENT_TYPE_DICT:
            return _CONTENT_TYPE_DICT[filetype]
    except:
        return _CONTENT_TYPE_DICT["json"] 

async def send_json( response, filename, cache=USE_CACHE ):
    await response.send_file( filename, 
                        max_age=MAX_AGE,
                        content_type=_CONTENT_TYPE_DICT["json"],
                        buf_size=FILE_BUF_SIZE) 

async def simple_response( message, response ):
    if message == "ok":
        resp = { "result": "ok"}
    else:
        resp = {"alert": message }
    await response.send( json.dumps( resp ))

# Index page
@app.route("/", save_headers=["User-Agent"] )
async def index_page( request, response ) :
    ipg = "/static/" + config.cfg.get( "initial_page", "index") + ".html"
    await response.redirect( ipg )

# File related web requests
@app.route("/static/<filepath>", save_headers=["User-Agent"])
async def static_files(request, response, filepath ):
    global _pages_served
    ua = request.headers.get(b'User-Agent')
    if ua:
        if b'Chrome' not in ua and b'Firefox' not in ua:
            # Could not make run Javascript await fetch in Safari.
            _logger.debug(f"Browser not supported {ua}")
            #raise tinyweb.HTTPException(403) # Forbidden
            await response.start_html()
            await response.send( "Safari not supported, use Chrome or Firefox" )
            return
        
    register_activity( request )
    
    if ".html" in filepath:
        _pages_served += 1
        
        # Check if page allowed
        mode = modes.get_mode()
        allowed_list = _ALLOWED_PAGES[mode]
        if filepath not in allowed_list:
            _logger.debug(f"{filepath} not allowed in mode {mode}")
            if _pages_served == 1 and "index.html" not in filepath:
                await response.redirect( "index.html" )
            else:
                await response.start_html()
                await response.send( f"Page not allowed in this mode: {modes.get_mode()}" )
            return

        
        
    filename = STATIC_FOLDER + filepath
    await response.send_file( filename, 
                            max_age=MAX_AGE,
                            content_type=get_content_type( filename ),
                            buf_size=FILE_BUF_SIZE ) 
 
@app.route("/data/<filepath>")
async def data_files( request, response, filepath ):
    register_activity( request )
    filename = DATA_FOLDER + filepath
    await response.send_file( filename, 
                        max_age=0,
                        content_type=get_content_type( filename ),
                        buf_size=FILE_BUF_SIZE) 

@app.route("/tunelib_json")
async def send_tunelib_file( request, response ):
    await send_json( response, config.MUSIC_JSON, cache=USE_CACHE )
    

@app.route("/get_progress" )
async def get_progress( request, response ):
    # Get progress of current tune
    # When playing music, /get_progress is good indicator of activity
    register_activity( request )

    progress = setlist.get_progress()
        
    await response.send( json.dumps( progress ))

@app.route("/queue_tune/<tune>")
async def queue_tune( request, response, tune ):
    # Queue tune to setlist
    setlist.queue_tune( tune )
    # Wait for setlist process to catch up
    await asyncio.sleep_ms( 500 )
    await get_progress( request, response )


            
@app.route("/start_tune")
async def go_tempo( request, response ):
    setlist.start_tune()
    # Wait for setlist process to catch up
    await asyncio.sleep_ms( 400 )
    await get_progress( request, response )


@app.route("/stop_tune_setlist" )
async def stop_tune_setlist( request, response ):
    setlist.stop_tune()
    # Wait for setlist process to catch up
    await asyncio.sleep_ms( 400 )
    await get_progress( request, response )
    

@app.route("/back_setlist" )
async def back_setlist( request, response ):
    setlist.to_beginning_of_tune()
    await asyncio.sleep_ms( 400 )
    await get_progress( request, response )

@app.route("/save_setlist")
async def save_setlist( request,response ):
    setlist.save()
    await simple_response( "ok", response )

@app.route("/load_setlist")    
async def load_setlist( request,response ):
    setlist.load()
    await get_progress( request, response )

@app.route("/clear_setlist")    
async def clear_setlist( request,response ):
    setlist.clear()
    await get_progress( request, response )

@app.route("/up_setlist/<pos>")    
async def up_setlist( request,response, pos ):
    setlist.up( int(pos) )
    await get_progress( request, response )

@app.route("/down_setlist/<pos>")    
async def down_setlist( request,response, pos ):
    setlist.down(int(pos) )
    await get_progress( request, response )

@app.route("/shuffle_set_list")
async def shuffle_set_list( request, response ):
    setlist.shuffle()
    await get_progress( request, response )
    
@app.route("/shuffle_all_tunes")
async def shuffle_all_tunes( request, response ):
    setlist.shuffle_all_tunes()
    await get_progress( request, response )

# Organ tuner web requests

@app.route("/note/<midi_note>")
async def note_page( request, response, midi_note ):
    await static_files( request, response, "note.html")


@app.route("/tune_all")
async def start_tune_all( request, response  ):
    organtuner.tune_all()
    await send_json( response, config.ORGANTUNER_JSON, cache=False )


@app.route("/start_tuning/<midi_note>")
async def start_tuning( request, response, midi_note ):
    # Tune one note
    organtuner.queue_tuning( ("tune", int(midi_note) ) ) 
    await send_json( response, config.ORGANTUNER_JSON, cache=False )

@app.route("/sound_note/<midi_note>")
async def sound_note( request, response, midi_note ):
    organtuner.queue_tuning( ("note_on",  int(midi_note) )) 
    await send_json( response, config.ORGANTUNER_JSON, cache=False )

@app.route("/sound_repetition/<midi_note>")
async def sound_repetition( request, response, midi_note ):
    organtuner.queue_tuning( ("note_repeat", int(midi_note) ) ) 
    await send_json( response, config.ORGANTUNER_JSON, cache=False )


@app.route("/scale_test")
async def scale_test( request, response ):
    organtuner.queue_tuning( ("scale_test", 0 ) ) 
    await send_json( response, config.ORGANTUNER_JSON, cache=False )


    
@app.route("/clear_tuning")
async def scale_test( request, response ):
    organtuner.clear_tuning() 
    await send_json( response, config.ORGANTUNER_JSON, cache=False )


# Keyboard mode web requests, keyboard.html page 
@app.route("/keyboard_status" )
async def keyboard_status( request, response ):
    # await response.start_html()
    s = json.dumps( soleble.get_status() )
    _logger.debug(f"/keyboard_status={s}" ) 
    await response.send( s )


# Battery information web request, common to most pages, called from common.js  
@app.route("/battery")
async def get_battery_status( request, response ):
    # When playing music, /battery is good indicator of activity
    register_activity( request )
    await response.send( json.dumps( battery.get_info() ) )

# Index.html page web requests

@app.route("/get_mode")
async def get_mode( request, response ):
    await response.send( json.dumps( { "mode" : modes.get_mode() } ) )

@app.route("/change_mode/<newmode>")
async def change_mode( request, response, newmode ):
    modes.change_mode( newmode )
    set_mode( )
    await response.send( "{}" )   
  
@app.route("/valid_modes")
async def valid_modes( request, response ):
    await response.send( json.dumps( config.cfg["modes"] ) )
 
@app.route("/battery_zero")
async def battery_zero( request, response ):
    battery.set_to_zero()
    await response.send( json.dumps( battery.get_info() ) )


@app.route("/errorlog")
async def show_log( request, response ):
    # Format log as HTML, only last log is shown.
    await response.start_html()
    await response.send( "<head></head><body><table>" )
    with open( _logger.get_filename() ) as file:
        while True:
            s = file.readline()
            if s == "":
                break
            if s[0:1] == " ":
                # This happens for exception traceback, put traceback info in column 3
                await response.send( "<tr><td></td><td></td><td></td><td>" + s + "</td></tr>" )
            else:
                await response.send( "<tr>" )
                for p in s.split(" - "):
                    await response.send( "<td>" + p + "</td>" )
                await response.send( "</tr>" )
    await response.send( '</table><br id="last"></body>' )
    await response.send( "<script>" )
    await response.send( 'document.getElementById("last").scrollIntoView(false);' )
    await response.send( "</script>" )

# diag.html web requests 	
@app.route("/diag")
async def diag( request, response ):

    # With ESP32S3 8 MB SPIRAM getting memory info takes 410 millisec
    # Collect=110ms, mem_free=150ms, mem_alloc=150ms
    async with scheduler.RequestSlice("webserver gc.collect", 150, 1000 ):
        gc.collect() # This is rather slow with 8MB
    async with scheduler.RequestSlice("webserver gc.mem_free", 200, 1000 ):
        free_ram = gc.mem_free() # This is rather slow with 8MB
    async with scheduler.RequestSlice("webserver gc.mem_alloc", 200, 1000 ):
        used_ram = gc.mem_alloc() # This is rather slow with 8MB

    async with scheduler.RequestSlice("webserver os.statvfs", 500, 1000 ):
        vfs = os.statvfs("/")
    block_size = vfs[0]
    
    try:
        midi_files = tunelist.get_tune_count()
    except:
        midi_files = ""
    
    tzoffset = config.get_float("time_zone_offset", 0)
    if tzoffset  <= 24:
        now = time.localtime( time.time() + int(tzoffset*3600))
    else:
        now = ttz.now()

    reboot_mins = time.ticks_diff( time.ticks_ms(), config.boot_ticks_ms )/ 1000 /60
    d = {
        "description": config.cfg["description"],
        "name": config.cfg["name"],
        "microcontroller": config.architecture,
        "mp_version": os.uname().version,
        "mp_bin": sys.implementation._machine,
        "last_refresh": f"{now[0]}/{now[1]}/{now[2]} {now[3]:02d}:{now[4]:02d}:{now[5]:02d}",
        "reboot_mins" : reboot_mins,
        "free_flash" : vfs[0]*vfs[3],
        "used_flash" : vfs[0]*(vfs[2]-vfs[3]),
        "free_ram": free_ram,
        "used_ram": used_ram,
        "solenoid_devices": solenoid.get_status(),
        "operating_mode" : modes.get_mode(),
        "midi_files" : midi_files,
        "music_folder": config.MUSIC_FOLDER,
        "logfilename": _logger.get_filename(),
        "errors_since_reboot": _logger.get_error_count()
        }
    await response.send( json.dumps( d ) ) 


@app.route("/wifi_scan")
async def wifi_scan( request, response ):
    await response.send( json.dumps( wifimanager.sta_if_scan() ) )

@app.route("/get_wifi_status")
async def get_wifi_status( request, response ):
    register_activity( request )
    c = wifimanager.get_status()
    now = time.ticks_ms()
    c["client_IPs"] = "".join([ ip+" " for ip in client_activity 
                        if time.ticks_diff( now, client_activity[ip] )< 10_000 ])
    await response.send( json.dumps( c ) )


# Play page web requests
@app.route("/set_velocity/<vel>")
async def set_velocity( request, response, vel ):
    _logger.debug(f"/set_velocity {vel}")
    tachometer.set_velocity( int(vel) )
    await get_progress( request, response )

@app.route("/top_setlist/<pos>")    
async def down_setlist( request,response, pos ):
    setlist.top(int(pos) )
    await get_progress( request, response )

@app.route("/drop_setlist/<pos>")    
async def drop_setlist( request,response, pos ):
    setlist.drop(int(pos) )
    await get_progress( request, response )

# Configuration change
@app.route("/verify_password", methods=["GET", "POST"],
           save_headers=["Content-Length","Content-Type"])
async def verify_password( request, response ):
    data = await request.read_parse_form_data()
    if modes.change_mode( "config", data["password"] ):
        resp = "ok" 
    else:
        resp = "Incorrect password"
    await simple_response( resp, response )

@app.route("/get_config")
async def get_config( request, response ):
    await response.send( json.dumps( config.get_config() ) )


@app.route("/save_config", methods=["GET", "POST"],
           save_headers=["Content-Length","Content-Type"])
async def change_config( request, response ):
    data = await request.read_parse_form_data()
    resp = config.save( data )
    await simple_response( resp, response )
 	
@app.route("/start_ftp", methods=["GET", "POST"],
           save_headers=["Content-Length","Content-Type"])
async def start_ftp( request, response ):
    data = await request.read_parse_form_data()

    if config.verify_password( data["password"] ):
        resp = "ok"
        # Run FTP in a separate thread
        import _thread
        def uftpd_in_a_thread():
            import uftpd
            _logger.info( "uftp started" )
        _thread.start_new_thread( uftpd_in_a_thread, () )
       
    else:
        resp = "Incorrect password"
    await simple_response( resp, response )
    
# Pinout functions
@app.route("/pinout_list" )
async def pinout_list( request, response ):
    _logger.debug("enter pinout_list")
    await response.send( json.dumps( pinout.pinout_list()) )

@app.route("/pinout_detail")
async def pinout_detail( request, response ):
    filename = pinout.get_pinout_filename()
    await send_json( response, config.DATA_FOLDER + "/" + filename, cache=False )

@app.route("/get_pinout_filename")
async def get_pinout_filename( request, response ):
    resp = { "pinout_filename": pinout.get_pinout_filename()}
    await response.send( json.dumps( resp ))
    
@app.route("/save_pinout_filename", methods=["GET", "POST"],
           save_headers=["Content-Length","Content-Type"])
async def save_pinout_filename( request, response ):
    data = await request.read_parse_form_data()
    
    pinout.set_pinout_filename( data["pinout_filename"] )
    await simple_response( "ok", response )

@app.route("/save_pinout_detail", methods=["GET", "POST"],
           save_headers=["Content-Length","Content-Type"],
           max_body_size=4096,)
async def save_pinout_detail( request, response ):
    _logger.debug("/save_pinout_detail entered")
    data = await request.read_parse_form_data()
    _logger.debug(f"save_pinout_detail received {len(data)=} elements")
    pinout.save( data )
    _logger.debug(f"save_pinout_detail pinoupt.save complete")
    await simple_response( "ok", response )
    
    
@app.route("/test_mcp", methods=["GET", "POST"],
           save_headers=["Content-Length","Content-Type"])
async def test_mcp( request, response ):
    data = await request.read_parse_form_data()
    await pinout.web_test_mcp( int(data["sda"]), int(data["scl"]), int(data["mcpaddr"]), int(data["pin"]))
    await simple_response( "ok", response )

@app.route("/test_gpio", methods=["GET", "POST"],
           save_headers=["Content-Length","Content-Type"])
async def test_gpio( request, response ):
    data = await request.read_parse_form_data()
    await pinout.web_test_gpio( int(data["pin"]))
    await simple_response( "ok", response )
                      

# Generic requests requests: some browsers request favicon
@app.route("/favicon.ico")    
async def serve_favicon( request,response ):
    await static_files( request, response, "favicon.ico" )

@app.route("/favicon.png")
async def static_favicon( request, response ):
    await static_files( request, response, "favicon.png" )
 

@app.catchall()
async def catchall_handler( request, response ):
    _logger.error(f"catchall_handler unknown request= {request.path.decode()}")
    #raise tinyweb.HTTPException(404)
    await response.redirect( "/" )


async def run_webserver(  ):
    global _logger, USE_CACHE, FILE_BUF_SIZE, MAX_AGE
    global STATIC_FOLDER, DATA_FOLDER
    
    _logger = getLogger(__name__)
    
    DATA_FOLDER = "data/"
    if _file_exists("software/static/"):
        STATIC_FOLDER = "software/static/"
    else:
        STATIC_FOLDER = "static/"


    # Configure file cache for browser
    if not config.cfg.get("webserver_cache", True):
        MAX_AGE = 0
        USE_CACHE = False
    else:
        MAX_AGE = config.get_int("max_age", 24*60*60)

        
    # Configure chunk size to send files
    if config.large_memory:
        FILE_BUF_SIZE = 4096
    else:
        FILE_BUF_SIZE = 128
        
    _logger.info(
        f"{USE_CACHE=} {MAX_AGE=:,} sec, send_file {FILE_BUF_SIZE=} bytes")
    await app.run( host='0.0.0.0', port=80 )

async def shutdown():
    await app.shutdown()
