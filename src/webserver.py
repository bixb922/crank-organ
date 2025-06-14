# (c) 2023 Hermann Paul von Borries
# MIT License
# Webserver module, serves all http requests.

# >>> redirect 404 to index page or to own page.

import os
import sys
import gc
import asyncio
from time import ticks_ms, ticks_diff
from random import getrandbits

from microdot import Microdot, send_file, redirect, Request, urldecode_bytes
# This is for filemanager, maximum file size to upload
Request.max_content_length = 1_000_000
Request.max_body_length = 1_000_000

from compiledate import compiledate
from minilog import getLogger
import scheduler
import fileops

import filemanager
# Everything is needed here
from drehorgel import battery, tunemanager, config, history, player, setlist, crank
from drehorgel import gpio, actuator_bank, timezone, poweroff
from drehorgel import led, wifimanager, plist, gpio

from pinout import GPIOstatistics, SaveNewPinout

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
MAX_AGE = config.get_int("max_age") or (24 * 60 * 60)


# Shows webserver processing time (total time is much higher)
@app.before_request
def func_before_req( request ):
    request.g.t0 = ticks_ms()


@app.after_request
def func_after_req( request, response ):
    try:
        this_session:dict = get_session( request )
    except KeyError:
        # No cookie - must send cookie and add new session
        # By design, this session cookie is different from the
        # boot_session_id. The boot session id identifies a
        # boot session, i.e. changes from one reboot to
        # the next reboot. Whereas the session cookie is issued
        # per client as a login session id to keep the login
        # state on this server from one request to the next.
        # 24+24=48 bits = 12 bytes hexa
        session_id = hex(getrandbits(24))[2:]+hex(getrandbits(24))[2:]
        response.set_cookie("session", session_id, path="/" )
        # If password_required, then login starts as False
        # If not password_required, then login will be always True
        this_session = {"login":not config.cfg["password_required"]}
        # Session information will be lost with each reboot, i.e.
        # it is NOT kept in flash. This means a user is logged out
        # on reboot.
        sessions[session_id] = this_session
    this_session["last_activity"] = ticks_ms()
    this_session["ip"] = request.client_addr[0]
    dt = ticks_diff( ticks_ms(), request.g.t0 )
    _logger.debug(f"{request.method} {request.url} {response.status_code}, {dt} msec")
    return response

def is_active(since_msec=60_000):
    # This is used by poweroff.py
    # Return true if recent web activity
    now = ticks_ms()
    return any( 
            s for s in sessions.values()
            if ticks_diff(now, s["last_activity"]) <= since_msec
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
# func MUST be a async function 
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
        return respond_error_alert("Password required"), 401
    return wrapper

organtuner_instance = None
def get_organ_tuner():
    global organtuner_instance
    if not organtuner_instance:
        from organtuner import OrganTuner
        organtuner_instance = OrganTuner( gpio.microphone_pin )
    return organtuner_instance
# call get_organ_tuner() in run_webserver() to load tuner at startup.    
   

@app.post("/verify_password")
async def verify_password( request ):
    # This is a "login" service: if password is correct
    # them mark session as logged in.
    # Logout is by rebooting the microcontroller.
    password = request.json.get("password")
    if config.verify_password( password, request.cookies["session"] ):
        try:
            get_session( request )["login"] = True
            return respond_ok()
        except KeyError:
            # Browser session does not exist in this server
            pass
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
async def get_description(request):    
    # Return description of this microcontroller, to be used
    # as the title of page. The browser client
    # caches this in tab storage. 
    return { "description": config.cfg.get("description")}

def get_progress():
    # Gather progress from all sources
    # Also used by mcserver (if present)
    progress = player.get_progress()
    crank.complement_progress(progress)
    setlist.complement_progress(progress)
    # gpio has th RegisterBank() object
    gpio.get_registers().complement_progress(progress)
    tunemanager.complement_progress(progress)
    return progress


@app.route("/get_progress/<browser_boot_session>")
async def process_get_progress(request, browser_boot_session):
    # Currently not using the browser_boot_session here
    # But the javascript uses it to flush cache.
    # If browser_boot_session is different than progress["boot_session"]
    # then this is the first /get_progress after reboot.
    # The browser then will, for example, invalidate the tab
    # cache to get fresh data.
    return get_progress()

#
# Setlist management
#

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

@app.route("/up_setlist/<tuneid>")
async def up_setlist(request, tuneid):
    setlist.up(tuneid)
    return get_progress()


@app.route("/down_setlist/<tuneid>")
async def down_setlist(request, tuneid):
    setlist.down(tuneid)
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
async def shuffle_3stars(request):
    setlist.shuffle_3stars()
    return get_progress()

#
# Organ tuner web requests
#
@app.route("/get_organtuner_json")
async def get_organtuner_json( request ):
    return get_organ_tuner().get_organtuner_json();

@app.route("/note/<int:pin_index>")
async def note_page(request, pin_index):
    return static_files( request, "note.html" )

@app.route("/tune_all")
async def start_tune_all(request):
    # All tuning requests (except clear_tuning)
    # just queue the operation and respond, so
    # it's not of interest to return organtuner.json
    # in these functions
    get_organ_tuner().tune_all()
    return respond_ok()


@app.route("/start_tuning/<int:pin_index>")
async def start_tuning(request, pin_index):
    # Tune one note
    get_organ_tuner().queue_tuning(get_organ_tuner().wait, 1000 )
    get_organ_tuner().queue_tuning(get_organ_tuner().update_tuning, pin_index)
    return respond_ok()


@app.route("/sound_note/<int:pin_index>")
async def sound_note(request, pin_index):
    get_organ_tuner().queue_tuning(get_organ_tuner().sound_note, pin_index)
    return respond_ok()


@app.route("/sound_repetition/<int:pin_index>")
async def sound_repetition(request, pin_index):
    get_organ_tuner().queue_tuning(get_organ_tuner().repeat_note, pin_index)
    return respond_ok()


@app.route("/scale_test")
async def scale_test(request):
    get_organ_tuner().queue_tuning(get_organ_tuner().scale_test, 0)
    return respond_ok()

@app.route("/all_pin_test")
async def all_pin_test(request):
    get_organ_tuner().queue_tuning(get_organ_tuner().all_pin_test, 0)
    return respond_ok()


@app.route("/clear_tuning")
async def clear_tuning(request):
    get_organ_tuner().clear_tuning()
    return respond_ok()


@app.route("/stop_tuning")
async def stop_tuning(request):
    get_organ_tuner().stop_tuning()
    return respond_ok()

@app.route("/get_tuning_stats")
async def get_tuning_stats(request):
    return get_organ_tuner().get_stats()  

# Battery information web request, common to most pages, called from common.js
@app.route("/battery")
async def get_battery_status(request):
    # When playing music, /battery is good indicator of activitys
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
    # It's now faster with latest MicroPython version,
    # gc.collect() now about 50 ms.
    # After PR#8183, even faster gc.collect() should be possible.
    try:
        async with scheduler.RequestSlice("webserver diag", 5000, 10_000):
            gc.collect()
            t0 = ticks_ms()
            # gc.collect() takes 50 to 100 ms.
            gc.collect()  # measure optimal gc.collect() time
            t1 = ticks_ms()
            gc_collect_time = ticks_diff(t1, t0)
            # mem_free and mem_alloc are quite slow, similar to
            # gc.collect()
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
    time_zone_info = f'{tz["longName"]}, {tz["shortName"]}, offset={round(-tz["offset"]/60.0)} min'

    reboot_sec = round(ticks_diff(ticks_ms(), config.boot_ticks_ms) / 1000 )
    d = {
        "description": config.cfg["description"],
        "name": config.cfg["name"],
        "mp_version": os.uname().version,
        "mp_bin": sys.implementation._machine, # type:ignore
        "last_refresh": now,
        "time_zone_info":  time_zone_info,
        "reboot_mins": f"{reboot_sec//60}:{reboot_sec%60:02d}",
        "free_flash": vfs[0] * vfs[3],
        "used_flash": vfs[0] * (vfs[2] - vfs[3]),
        "free_ram": free_ram,
        "used_ram": used_ram,
        "gc_collect_time": gc_collect_time,
        "max_gc_collect_time": scheduler.max_gc_time,
        "solenoid_devices": "".join(f"{drv} {pins} pins\n" for drv, pins in actuator_bank.get_status()),
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
    now = ticks_ms()
    def seconds_since_last( session ):
        return round(ticks_diff( now, session["last_activity"] )/1000)
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

@app.route("/top_setlist/<tuneid>")
async def top_setlist(request, tuneid):
    setlist.top(tuneid)
    return get_progress()


@app.route("/drop_setlist/<tuneid>")
async def drop_setlist(request, tuneid):
    setlist.drop(tuneid)
    return get_progress()

#
# Changes to config.json
#

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

#
# Pinout functions
#

@app.route("/pinout_list")
async def pinout_list(request):
    return plist.get_filenames_descriptions()

@app.route("/get_pinout_filename")
async def get_pinout_filename(request):
    return {
        "pinout_filename": plist.get_saved_pinout_filename(),
        "pinout_description": plist.get_description(),
    }

@app.route("/get_used_pins/<path>")
async def get_used_pins( request, path ):
    return GPIOstatistics(decodePath(path)).get_used_pins()


@app.route("/get_index_page_info")
async def get_index_page_info(request):
    # Information needed by index.html
    resp = await get_pinout_filename(request)
    resp["servernode"] = config.cfg["servernode"]
    return resp


@app.post("/save_pinout_filename")
@authorize
async def save_pinout_filename(request):
    # Force reboot to make this take effect.
    setlist.stop_playback()
    data = request.json
    plist.set_current_pinout_filename(data["pinout_filename"])

    return respond_ok()


@app.post("/save_pinout_detail/<path>")
@authorize
async def save_pinout_detail(request, path):
    # Force reboot to use the player to make definitions take effect.
    # However, it's not mandatory to stop current tune and setlist,
    # unlike organtuner.
    setlist.stop_playback()
    output_filename = decodePath(path)
    try:
        # SaveNewPinout class will validate and do a init of pint
        SaveNewPinout(request.json, output_filename)
        _logger.debug("save_pinout_detail pinout.save complete")
        return respond_ok()
    except RuntimeError as e:
        _logger.debug(f"save_pinout_detail exception {repr(e)}")
        return respond_error_alert(f"pinout not saved: {repr(e)}")

@app.post("/test_pin")
async def test_pin( request ):
    setlist.stop_playback()
    from solenoid import PinTest
    alert_message = await PinTest().web_test_pin( request.json )
    if alert_message:
        return respond_error_alert( alert_message )
    return respond_ok()
    
@app.post("/test_drumdef")
async def test_drumdef( request ):
    # Drum definition does not stop playback, it's desirable
    # to use a MIDI to see how it works.
    from driver_ftoms import FauxTomDriver
    drumdef = request.json
    for pin in FauxTomDriver().get_pin_list():
        dd = drumdef[str(pin.nominal_midi_number)]
        pin.set_virtual_drum_characteristics( dd )
    return respond_ok()

@app.post("/save_drumdef")
async def save_drumdef( request ):
    # Don't disable music playback here, need to play
    # MIDI while testing drums.
    from driver_ftoms import FauxTomDriver
    FauxTomDriver().save( request.json )
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
    return {"progress":tunemanager.get_sync_progress()}

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
    reg = gpio.get_registers().factory( data["name"])
    reg.set_value(data["value"])
    return get_progress()

@app.route("/list_pinout_by_midi_note/<path>")
async def list_by_midi_note( request, path ):
    def sort_key( x ):
        # Sort by
        # program number
        # midi_number (should not be undefined i.e. None here)
        # register name
        return f"{x['program_number']:5d}{x['midi_number']}{x['actuator_note']:20s}{x['register_name'] or ' ':20s}"

    filename = decodePath( path )
    from midicontroller import RegisterBank
    from pinout import ActuatorDef

    # Parse the pinout.json here, don't disturb what is already
    # loaded. The result of parsing here is lost when exiting
    # list_midi_note.
    actuator_def = ActuatorDef(filename, RegisterBank()) # It's not necessare to store actuator_def
    controller = actuator_def.get_controller()
    notedef = []
    for action in controller.get_notedict().values():
        for actuator, reg, midi_note in action:
            notedef.append( {  
                             "program_number":midi_note.program_number, 
                             "midi_number":midi_note.midi_number, 
                             "midi_note": str(midi_note), 
                             "actuator_name": str(actuator), 
                             "actuator_note": str(actuator.nominal_midi_note) if actuator.nominal_midi_note else "", 
                             "actuator_rank": actuator.get_rank_name(), 
                             "register_name": reg.name,
                             "invert": False } )
    notedef.sort( key=sort_key )
                
    return notedef


#
# File manager
#

def decodePath( path ):
    # Inverse function to encodePath() in common.js
    return urldecode_bytes( path.encode() )

@app.route("/listdir")
@app.route("/listdir/")
@app.route("/listdir/<path>")
async def filemanager_listdir(request, path=""):
    listpath = decodePath(path)
    if listpath.endswith("filemanager.html"):
        # Don't navigate to /static/filemanager.html please.
        return respond_error_alert("Use /filemanager")
    return filemanager.listdir( listpath )

@app.route("/listdir_tunelib")
async def listdir_tunelib(request):
    return filemanager.fast_listdir( config.TUNELIB_FOLDER )

@app.route("/check_flash_full")
async def check_flash_full(request):
    fstat = filemanager.status()
    # Leave at leat 150 kb free when uploading.
    # Updating a file like tunelib.json or history.json needs to write the complete
    # file a second time, so there must at least be space for one additional copy of the file.
    # >>> calculate space depending on largest file in /data?
    if fstat["total_flash"]-fstat["used_flash"] < 150_000:
        return respond_error_alert("No se puede subir archivo, memoria flash casi llena")
    return respond_ok()


@app.post('/upload/<path_filename>')
@authorize
async def filemanager_upload(request, path_filename ):
    path, filename = path_filename.split("+")
    path = decodePath( path )
    filename = decodePath( filename )
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
async def show_midi( request, path ):
    # Javascript will retrieve the path passed in the URL
    return static_files( request, "show_midi.html" )

@app.route("/get_midi_file/<path>")
async def get_midi_file( request, path ):
    return filemanager.get_midi_file( decodePath( path )  )

@app.route("/used_flash")
async def filemanager_status(request):
    return filemanager.status()

@app.post("/delete_file")
@authorize
async def filemanager_delete(request):
    # Delete a file
    path = request.json["delete_filename"]
    try:
        filemanager.delete( decodePath( path )  )
    except Exception as e:
        # Can happen if there are 2 browser windows
        _logger.error(f"Error deleting file {path}: {e}")
        return respond_error_alert(f"Error {e} deleting file {path}")
    return respond_ok()

@app.post("/purge_tunelib_file")
@authorize
async def purge_tunelib_file(request ):
    # This filename was issued by this microcontroller.
    # No decoding necessary.
    filename = request.json["purge_filename"]
    filemanager.purge_tunelib_file(  filename )
    return respond_ok()

@app.route("/filemanager")
@app.route("/filemanager/")
@app.route("/filemanager/<path>")
async def handle_filemanager( request, path=""):
    # Load page, javascript will retrieve the path an call back
    return static_files( request, "filemanager.html" )


# A very simple call just to ask for password and get authorized
@app.route("/get_permission")
@authorize
async def get_permission( request ):
    return {} 

# Catchall handler to debug possible errors at html level
@app.get('/<path:path>')
async def catch_all(request, path):
    _logger.debug(f"***CATCHALL*** {path=} request=" + str(request))
    return "", 404

@app.errorhandler(RuntimeError)
async def runtime_error(request, exception):
    return respond_error_alert("RuntimeError exception detected")

# >>> this error stops the complete application, is raised to
# >>>  the global asyncio error handler (occurred only once in
# during a test situation)
# Traceback (most recent call last):
#   File "crank-organ/src/microdot.py", line 1333, in handle_request
#   File "crank-organ/src/microdot.py", line 397, in create
#   File "crank-organ/src/microdot.py", line 511, in _safe_readline
#   File "asyncio/stream.py", line 1, in readline
# OSError: [Errno 113] ECONNABORTED
# Was triggered when changing the WiFi network hotspot during operation
# from main to secondary router of same SSID. Browser
# reported "Network changed."
#
# Also seen with shaky WiFi connection, but this seems not to prevent
# the webserver from running.
#     Traceback (most recent call last):
# File "asyncio/core.py", line 1, in run_until_complete
# File "crank-organ/src/microdot.py", line 1227, in serve
# File "crank-organ/src/microdot.py", line 1339, in handle_request
# File "crank-organ/src/microdot.py", line 641, in write
# File "asyncio/stream.py", line 1, in stream_awrite
# File "asyncio/stream.py", line 1, in write
# OSError: [Errno 113] ECONNABORTED

@app.errorhandler(Exception)
async def error_handler( request, exception ):
    _logger.exc( exception, "Server error 500" )
    return respond_error_alert(f"Server error 500 {request.url=} {exception=}")

async def run_webserver():
    global _logger, USE_CACHE, MAX_AGE

    # Configure file cache for browser
    if not config.cfg.get("webserver_cache", True):
        MAX_AGE = 0
        USE_CACHE = False

    _logger.debug(f"{USE_CACHE=} {MAX_AGE=:,} sec")
    await app.start_server(host="0.0.0.0", port=80 )


async def shutdown():
    app.shutdown()
