# (c) 2023 Hermann Paul von Borries
# MIT License
# Webserver module, serves all http requests.


import os
import sys
import gc
import asyncio
import time
from random import getrandbits

from microdot import Microdot, send_file, redirect, Request, Response, urldecode_bytes
# This is for filemanager, maximum file size to upload
Request.max_content_length = 1_000_000
Request.max_body_length = 1_000_000

from minilog import getLogger
import scheduler
from config import config, password_manager
import fileops
import pinout
from battery import battery
from wifimanager import wifimanager
from solenoid import solenoids
from compiledate import compiledate

from tunemanager import tunemanager
from tachometer import crank

from setlist import setlist
from history import history
from timezone import timezone
from player import player
from organtuner import organtuner
from poweroff import poweroff
from led import led
from midi import registers, controller
import filemanager


app = Microdot()
_logger = getLogger(__name__)
DATA_FOLDER = "data/"
STATIC_FOLDER = "software/static/"

boot_session_id = hex(getrandbits(24))[2:]

# Session is a dict, key=session_id, session data is a dict, for example {"login":True}
sessions = {}
def get_session( request ):
    # Must use try/catch to get the cases where there is no session
    # This can happen with the first http request after a reboot.
    return sessions[request.cookies["session"]]

USE_CACHE = True  # will be set by run_webserver() to value in config.json
MAX_AGE = config.get_int("max_age", 24 * 60 * 60)


# Shows webserver processing time (total time is much higher)
@app.before_request
def func_before_req( request ):
    request.g.t0 = time.ticks_ms()


@app.after_request
def func_after_req( request, response ):
    try:
        this_session = get_session( request )
    except KeyError:
        # No cookie - must send cookie and add new session
        # 24+24=48 bits = 12 bytes hexa
        session_id = hex(getrandbits(24))[2:]+hex(getrandbits(24))[2:]
        response.set_cookie("session", session_id, path="/" )
        # If password_required, then login starts as False
        # If not password_required, then login will be always True
        this_session = {"login":not config.cfg["password_required"]}
        sessions[session_id] = this_session
    this_session["last_activity"] = time.ticks_ms()
    this_session["ip"] = request.client_addr[0]
    dt = time.ticks_diff( time.ticks_ms(), request.g.t0 )
    _logger.debug(f"{request.method} {request.url} {response.status_code}, {dt} msec")
    return response

def is_active(since_msec=60_000):
    # This is used by poweroff.py
    # Return true if recent web activity
    now = time.ticks_ms()
    return any( 
            s for s in sessions.values()
            if time.ticks_diff(now, s["last_activity"]) <= since_msec
            )

def respond_ok():
    # Absence of "error":True means "everything is ok"
    return {}

def respond_error_alert( alert_message ):
    # "alert": alert_message means: show this message to user
    # "error": True means: the browser javascript code should not
    # continue to run since things went bad
    # Currently no way to show alert with "error":False.
    return { "error":True, "alert": alert_message }

# Define own (async) decorator to check authorization
def authorize(func):
    async def wrapper(*args, **kwargs):
        try:
            # args[0] is the request object
            this_session = get_session( args[0] )
        except KeyError:
            this_session = {}
        # No need to check config.cfg["password_required"] because
        # that was checked when handing out the session cookie in after_request
        if this_session.get("login"):
            # Is login: authorized to call the function
            return await func(*args, **kwargs)
        # Not login: return 401 to force client to ask
        # for password.
        return "Password required", 401
    return wrapper

   
@app.post("/verify_password")
def verify_password( request ):
    # This is a "login" service: if password is correct
    # them mark session as logged in.
    # Logout is by rebooting the microcontroller.
    password = request.json.get("password")
    if password_manager.verify_password( password, request.cookies["session"] ):
        get_session( request )["login"] = True
        return respond_ok()
    return respond_error_alert("Password incorrect")


# Home page
@app.route("/")
async def index_page(request):
    inipage = "/static/index.html"
    return redirect(inipage)


# File related web requests
@app.route("/static/<filepath>")
async def async_static_files(request, filepath):
    return static_files( request, filepath )

def static_files( request, path ):
    ua = request.headers.get("User-Agent")
    if ua:
        if "Chrome" not in ua and "Firefox" not in ua:
            # Could not make run Javascript's "await fetch" well in Safari.
            _logger.debug(f"Browser not supported {ua}")
            return "Safari not supported, use Chrome or Firefox"

    filename = STATIC_FOLDER + path
    # Check first for uncompressed file. 
    # Could make it easier for development since
    # uploading a uncompressed file takes precedence.
    if fileops.file_exists(filename):
        return send_file(filename, max_age=MAX_AGE)
    
    # File not found, perhaps a compressed version exists?
    # In that case, add a header for the Content-type  according to file type
    # and a header for Content-Encoding = gzip
    filename_zip = filename + ".gz"
    if fileops.file_exists( filename_zip ):
        # If .gz file, serve this compressed file 
        # instead of regular file
        # On Mac, compress with gzip, for example:
        # gzip -9 -c -k config.html > config.html.gz
        # See https://www.gzip.org/
        # Content type depends on the original file type
        ct = filemanager.get_mime_type( filename )
        return send_file(filename_zip, max_age=MAX_AGE, compressed=True, content_type=ct)
    _logger.info(f"static_files {filename} not found")
    return "", 404


@app.route("/data/<filepath>")
async def send_data_file(request, filepath):
    filename = DATA_FOLDER + filepath
    if not fileops.file_exists(filename):
        _logger.info(f"send_data_file {filename} not found")
        return "", 404
    return send_file(filename, max_age=0)

@app.route("/get_description")
def get_description(request):    
    # Return description of this microcontroller, to be used
    # as the title of page   
    return { "description": config.cfg.get("description")}

def get_progress():
    # Gather progress from all sources
    # Also used by mcserver
    # >>> should be player.complement_progress()
    # >>> and start progress here 
    progress = player.get_progress()
    crank.complement_progress(progress)
    scheduler.complement_progress(progress)
    setlist.complement_progress(progress)
    registers.complement_progress(progress)
    return progress


@app.route("/get_progress/<browser_boot_session>")
async def process_get_progress(request, browser_boot_session):
    # Currently not using the browser_boot_session here
    # But the javascript uses it to flush cache.
    # If browser_boot_session is different than progress["boot_session"]
    # then this is the first /get_progress after reboot.
    return get_progress()


@app.post("/queue_tune/<tune>")
async def queue_tune_setlist(request, tune):
    # Queue tune to setlist
    setlist.queue_tune(tune)
    return get_progress()


@app.route("/start_tune")
async def start_tune_setlist(request):
    setlist.start_tune()
    return get_progress()


@app.route("/stop_tune_setlist")
async def stop_tune_setlist(request):
    setlist.stop_tune()
    return get_progress()


@app.route("/back_setlist")
async def back_setlist(request):
    setlist.to_beginning_of_tune()
    return get_progress()


@app.route("/save_setlist")
async def save_setlist(request):
    setlist.save()
    return get_progress()


@app.route("/load_setlist")
async def load_setlist(request):
    setlist.load()
    return get_progress()


@app.route("/clear_setlist")
async def clear_setlist(request):
    setlist.clear()
    return get_progress()


@app.route("/up_setlist/<int:pos>")
async def up_setlist(request, pos):
    setlist.up(pos)
    return get_progress()


@app.route("/down_setlist/<int:pos>")
async def down_setlist(request, pos):
    setlist.down(pos)
    return get_progress()


@app.route("/shuffle_set_list")
async def shuffle_set_list(request):
    setlist.shuffle()
    return get_progress()


@app.route("/shuffle_all_tunes")
async def shuffle_all_tunes(request):
    setlist.shuffle_all_tunes()
    return get_progress()

@app.route("/shuffle_3stars")
async def shuffle_all_tunes(request):
    setlist.shuffle_3stars()
    return get_progress()

# Organ tuner web requests


@app.route("/note/<int:pin_index>")
async def note_page(request, pin_index):
    return static_files( request, "note.html" )

@app.route("/tune_all")
async def start_tune_all(request):
    # All tuning requests (except clear_tuning)
    # just queue the operation and respond, so
    # it's not of interest to return organtuner.json
    # in these functions
    organtuner.tune_all()
    return respond_ok()


@app.route("/start_tuning/<int:pin_index>")
async def start_tuning(request, pin_index):

    # Tune one note
    organtuner.queue_tuning(organtuner.wait, 1000 )
    organtuner.queue_tuning(organtuner.update_tuning, pin_index)
    return respond_ok()


@app.route("/sound_note/<int:pin_index>")
async def sound_note(request, pin_index):
    organtuner.queue_tuning(organtuner.sound_note, pin_index)
    return respond_ok()


@app.route("/sound_repetition/<int:pin_index>")
async def sound_repetition(request, pin_index):
    organtuner.queue_tuning(organtuner.repeat_note, pin_index)
    return respond_ok()


@app.route("/scale_test")
async def scale_test(request):
    organtuner.queue_tuning(organtuner.scale_test, 0)
    return respond_ok()

@app.route("/all_pin_test")
async def all_pin_test(request):
    organtuner.queue_tuning(organtuner.all_pin_test, 0)
    return respond_ok()


@app.route("/clear_tuning")
async def clear_tuning(request):
    organtuner.clear_tuning()
    return send_file(config.ORGANTUNER_JSON)


@app.route("/stop_tuning")
async def stop_tuning(request):
    organtuner.stop_tuning()
    return respond_ok()


# Battery information web request, common to most pages, called from common.js
@app.route("/battery")
async def get_battery_status(request):
    # When playing music, /battery is good indicator of activity

    return battery.get_info()


# Index.html page web requests


@app.route("/battery_zero")
async def battery_zero(request):
    battery.set_to_zero()
    return battery.get_info()

@app.post("/record_battery_level")
async def record_battery_level(request):
    battery.record_level( request.json["level"]  )
    return battery.get_info()

@app.route("/errorlog")
async def show_log(request):
    # Show current error log
    filename = _logger.get_current_log_filename() 
    # Must be encoded like encodeURIComponent()
    filename = filename.replace( "/", "%2F" )
    return redirect( "/show_file/" + filename )

# diag.html web requests
@app.route("/diag")
async def diag(request):
    # Collect=110ms, mem_free=150ms, mem_alloc=150ms
    try:
        async with scheduler.RequestSlice("webserver diag", 5000, 10_000):
            gc.collect()
            t0 = time.ticks_ms()
            gc.collect()  # measure optimal gc.collect() time
            t1 = time.ticks_ms()
            gc_collect_time = time.ticks_diff(t1, t0)

            free_ram = gc.mem_free()  # This is rather slow with 8MB
            used_ram = gc.mem_alloc()  # This is rather slow with 8MB
            # statvfs takes 1.5 sec
            vfs = os.statvfs("/")

    except Exception:
        gc_collect_time = "?"
        free_ram = "?"
        used_ram = "?"
        vfs = (0, 0, 0, 0, 0, 0)

    try:
        midi_files = tunemanager.get_tune_count()
    except Exception:
        midi_files = ""

    now = timezone.now_ymdhmsz()
    tz = timezone.get_time_zone_info()
    time_zone_info = f'{tz[2]}, {tz[1]}, offset={round(-tz[0]/60.0)} min'

    reboot_sec = round(time.ticks_diff(time.ticks_ms(), config.boot_ticks_ms) / 1000 )
    d = {
        "description": config.cfg["description"],
        "name": config.cfg["name"],
        "mp_version": os.uname().version,
        "mp_bin": sys.implementation._machine,
        "last_refresh": now,
        "time_zone_info":  time_zone_info,
        "reboot_mins": f"{reboot_sec//60}:{reboot_sec%60:02d}",
        "free_flash": vfs[0] * vfs[3],
        "used_flash": vfs[0] * (vfs[2] - vfs[3]),
        "free_ram": free_ram,
        "used_ram": used_ram,
        "gc_collect_time": gc_collect_time,
        "solenoid_devices": solenoids.get_status(),
        "midi_files": midi_files,
        "tunelib_folder": config.TUNELIB_FOLDER,
        "logfilename": _logger.get_current_log_filename(),
        "errors_since_reboot": _logger.get_error_count(),
        "compile_date": compiledate,
        "crank_installed": crank.is_installed()
    }
    return d


@app.route("/reset")
async def reset_microcontroller(request):
    led.ack()
    asyncio.create_task(poweroff.wait_and_reset())
    return respond_ok()


@app.route("/deep_sleep")
async def deep_sleep(request):
    led.ack()
    asyncio.create_task(poweroff.wait_and_power_off())
    return respond_ok()


@app.route("/wifi_scan")
async def wifi_scan(request):
    return wifimanager.sta_if_scan()


@app.route("/get_wifi_status")
async def get_wifi_status(request):
    now = time.ticks_ms()
    def seconds_since_last( session ):
        return round(time.ticks_diff( now, session["last_activity"] )/1000)
    c = wifimanager.get_status()
    # Add clientes with activities in the last minutes
    c["client_IPs"] = "".join(
        (
            f'{s["ip"]}={seconds_since_last(s)}sec '
            for s in sessions.values()
        )
    )
    return c

@app.post("/set_time_zone")
async def update_time_zone(request):
    timezone.set_time_zone( request.json )
    return respond_ok()
        

# Play page web requests
@app.route("/set_velocity_relative/<int:change>")
async def set_velocity_relative(request, change):
    crank.set_velocity_relative(change)
    return get_progress()

@app.route("/tacho_irq_report")
def tacho_irq_report(request):
    return crank.td.irq_report()

@app.route("/top_setlist/<int:pos>")
async def top_setlist(request, pos):
    setlist.top(pos)
    return get_progress()


@app.route("/drop_setlist/<int:pos>")
async def drop_setlist(request, pos):
    setlist.drop(pos)
    return get_progress()


# Changes to config.json

@app.route("/get_config")
async def get_config(request):
    return config.get_config()

@app.post("/save_config")
@authorize
async def change_config(request):
    result = config.save(request.json)
    if result:
        return respond_error_alert(result)
    return respond_ok()

# Pinout functions
@app.route("/pinout_list")
async def pinout_list(request):
    return pinout.plist.get_filenames_descriptions()


@app.route("/pinout_detail")
async def pinout_detail(request):
    return send_file(pinout.plist.get_current_pinout_filename())


@app.route("/get_pinout_filename")
async def get_pinout_filename(request):
    return {
        "pinout_filename": pinout.plist.get_current_pinout_filename(),
        "pinout_description": pinout.plist.get_description(),
    }

@app.route("/get_used_pins")
def get_used_pins( request ):
    return pinout.GPIOstatistics().get_used_pins()


@app.route("/get_index_page_info")
async def get_index_page_info(request):
    # Information needed by index.html
    resp = await get_pinout_filename(request)
    server = config.cfg["servernode"]
    proto = ""
    if server != "":
        if not server.startswith("http"):
            if server.endswith(".com"):
                proto = "https://"
            else:
                proto = "http://"
            server = proto + server
    resp["serverlink"] = server

    return resp


@app.post("/save_pinout_filename")
@authorize
async def save_pinout_filename(request):
    data = request.json
    pinout.plist.set_current_pinout_filename(data["pinout_filename"])
    solenoids.init_pinout()

    # Organtuner be aware: organtuner.json may no longer
    # be valid
    organtuner.clear_tuning()
 
    return respond_ok()


@app.post("/save_pinout_detail")
@authorize
async def save_pinout_detail(request):
    try:
        pinout.SaveNewPinout(request.json)
        # SaveNewPinout class will validate and do a init of pint
        organtuner.clear_tuning()
        solenoids.reinit()
        _logger.debug("save_pinout_detail pinout.save complete")
        return respond_ok()
    except RuntimeError as e:
        _logger.debug(f"save_pinout_detail exception {repr(e)}")
        return respond_error_alert(f"pinout not saved: {repr(e)}")


@app.post("/test_mcp")
async def test_mcp(request):
    data = request.json
    await pinout.test.web_test_mcp(
        int(data["sda"]),
        int(data["scl"]),
        int(data["mcpaddr"]),
        int(data["pin"]),
    )
    return respond_ok()


@app.post("/test_gpio")
async def test_gpio(request):
    data = request.json
    await pinout.test.web_test_gpio(int(data["pin"]))
    return respond_ok()


# Generic requests requests: some browsers request favicon
@app.route("/favicon.ico")
async def serve_favicon(request):
    return send_file(STATIC_FOLDER + "favicon.ico", max_age=MAX_AGE)


@app.route("/favicon.png")
async def static_favicon(request):
    return send_file(STATIC_FOLDER + "favicon.png", max_age=MAX_AGE)


# Not used
@app.route("/logout")
async def logout(request): 
    get_session( request )["login"] = False
    return {}


# Tunelib editor

@app.route("/start_tunelib_sync")
async def start_tunelib_sync(request):
    tunemanager.start_sync()
    return respond_ok()


# Tunelib editor
@app.route("/tunelib_sync_progress")
async def tunelib_sync_progress(request):
    return {"progress":tunemanager.sync_progress()}


#
# Tunelib editor
@app.post("/save_tunelib")
@authorize
async def save_tunelib(request):
    tunemanager.save(request.json)
    return respond_ok()


@app.post("/save_lyrics")
@authorize
async def save_lyrics( request ): 
    data = request.json
    tunemanager.save_lyrics( data["tuneid"], data["lyrics"])
    return respond_ok()

@app.route("/delete_history/<int:days>")
@authorize
async def delete_history(request, days):
    history.delete_old(days)
    return respond_ok()

@app.post( "/register_comment")
async def register_comment(request):
    # Register comment does not ask for password
    # The purpose is to register rating/comment during the performance
    # so this has to be easy to use.
    data = request.json
    tunemanager.register_comment( data["tuneid"], data["comment"])
    return respond_ok()

@app.post( "/tempo_follows_crank" )
async def tempo_follows_crank( request ):
    data = request.json
    player.set_tempo_follows_crank( data["tempo_follows_crank"] )
    return get_progress()

@app.post( "/toggle_register")
async def toggle_register( request ):
    data = request.json
    reg = registers.factory( data["name"])
    reg.toggle()
    return get_progress()

@app.get("/list_pinout_by_midi_note")
def list_by_midi_note( request ):
    def sort_key( x ):
        # Sort by
        # program number
        # midi_number (should not be undefined i.e. None here)
        # register name
        return f"{x['program_number']:5d}{x['midi_number']}{x['solepin_note']:20s}{x['register_name'] or ' ':20s}"

    # Output listing of definition, ordered by midi note
    notedef = []
    for plist in controller.get_notedict().values():
        for solepin, reg, midi_note in plist:
            notedef.append( {  "program_number":midi_note.program_number, 
                             "midi_number":midi_note.midi_number, 
                             "midi_note": str(midi_note), 
                             "solepin_name": solepin.name, 
                             "solepin_note": str(solepin.midi_note), 
                             "solepin_rank": solepin.rank, 
                             "register_name": reg.name} )
    notedef.sort( key=sort_key )
                
    return notedef


#
# File manager
#

def decodePath( path ):
    return urldecode_bytes( path.encode() )

@app.route("/listdir")
@app.route("/listdir/")
@app.route("/listdir/<path>")
async def filemanager_listdir(request, path=""):
    return filemanager.listdir( decodePath(path) )


@app.post('/upload/<path_filename>')
@authorize
async def filemanager_upload(request, path_filename ):
    path, filename = path_filename.split("+")
    try:
        return filemanager.upload( request, path, filename  )
    except ValueError:
        return respond_error_alert("Error, No destination folder could be assigned, unknown file type")

@app.route("/download/<path>")
async def filemanager_download(request, path):
    # Download a file from the microcontroller to the PC
    return filemanager.download( decodePath( path ) )

@app.route("/show_file/<path>")
async def filemanager_show_file( request, path ):
    return filemanager.show_file( decodePath( path ) ) 

@app.route("/show_midi/<path>")
def show_midi( request, path ):
    # Javascript will decode the path passed in the URL
    return static_files( request, "show_midi.html" )

@app.route("/get_midi_file/<path>")
def get_midi_file( request, path ):
    return filemanager.get_midi_file( decodePath( path )  )

@app.route("/used_flash")
async def filemanager_status(request):
    return filemanager.status()

@app.route("/delete_file/<path>")
@authorize
async def filemanager_delete(request, path):
    # Delete a file
    try:
        filemanager.delete( decodePath( path )  )
    except Exception as e:
        # Probability of this happening is nil...???
        return respond_error_alert(f"Error {e} deleting file {path}")
    return respond_ok()

@app.route("/filemanager")
@app.route("/filemanager/")
@app.route("/filemanager/<path>")
async def handle_filemanager( request, path=""):
    # Load page, javascript will handle the rest.
    return static_files( request, "filemanager.html" )

@app.route("/set_playback_disabled")
def set_playback_enabled( request ):
    # note.html and notelist.html disable playback
    # so no MIDI files will be played accidentally during tuning
    # To re-enable, reboot.
    scheduler.set_playback_mode(False)
    return respond_ok()


# Catchall handler to debug possible errors at html level
@app.get('/<path:path>')
def catch_all(request, path):
    _logger.debug(f"***CATCHALL*** {path=} request=" + str(request))
    return "", 404

@app.errorhandler(RuntimeError)
def runtime_error(request, exception):
    return respond_error_alert("RuntimeError exception detected")

@app.errorhandler(500)
def error500(request):
    return respond_error_alert(f"Server error 500 {request.url=}")

async def run_webserver():
    global _logger, USE_CACHE, MAX_AGE

    # Configure file cache for browser
    if not config.cfg.get("webserver_cache", True):
        MAX_AGE = 0
        USE_CACHE = False

    _logger.debug(f"{USE_CACHE=} {MAX_AGE=:,} sec")
    await app.start_server(host="0.0.0.0", port=80 )


async def shutdown():
    await app.shutdown()
