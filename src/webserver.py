# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
# Webserver module, serves all http requests.

# >>> check if multipart/form-data is better than shipping json.
# >>> some day, update Microdot to last version (size increase!)
# >>> evaluate Microdot native authorization


import os, sys, gc, asyncio
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
from midi import NoteDef

# Everything is needed here
from drehorgel import battery, tunemanager, config, history, setlist, player, crank
from drehorgel import gpio, actuator_bank, timezone
from drehorgel import wifimanager, gpio, poweroff
from solenoid import PinTest

app = Microdot()
_logger = getLogger(__name__)

# Priority: software/static (if it there) to allow
# incremental software update and development
# If one of these folders is not there, no significant overhead is incurred.
_STATIC_FOLDERS = ("/software/static/", "/rom/static/")


# Session is a dict, key=session_id, session data is a dict, for example {"login":True}
sessions = {}
def get_session( request ):
    # Must use try/catch to get the cases where there is no session
    # This can happen with the first http request after a reboot.
    return sessions[request.cookies["session"]]

MAX_AGE = config.max_age


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
        # boot_session id (set by player.py). The boot session id identifies a
        # boot session, i.e. changes from one reboot to
        # the next reboot. Whereas the session cookie is issued
        # per client as a login session id to keep the login
        # state on this server from one request to the next.
        # 24+24=48 bits = 12 bytes hexa
        session_id = hex(getrandbits(24))[2:]+hex(getrandbits(24))[2:]
        response.set_cookie("session", session_id, path="/" )
        # If password_required, then login starts as False
        # If not password_required, then login will be always True
        this_session = {"login":not config.password_required}
        # Session information will be lost with each reboot, i.e.
        # it is NOT kept in flash. This means a user is logged out
        # on reboot.
        sessions[session_id] = this_session
        # _logger.debug(f"New session from IP {request.client_addr[0]}")
    this_session["last_activity"] = ticks_ms()
    this_session["ip"] = request.client_addr[0]
    dt = ticks_diff( ticks_ms(), request.g.t0 )
    _logger.debug(f"{request.method} {request.url} {response.status_code}, {dt} msec")
    return response


def is_active(since_msec=60_000, ip_prefix=""):
    # Return true if recent web activity
    # iprange="": test for activity on all client IP addresses
    # ip_prefix="192.168.144": test for activity on all address
    # starting with that prefix
    now = ticks_ms()
    return any( 
            s for s in sessions.values()
            if ticks_diff(now, s["last_activity"]) <= since_msec
            and s["ip"].startswith(ip_prefix)
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

def respond_not_found( ):
    # Returning an error page makes it clearer what error
    # occurred, if not it's easy to mistake for a connection error.
    error_page = "<big>404 page not found. <a href='/'>To index page.</a>"
    # Must return 404 error in case the caller of the
    # file is fetch_json(), for example for json files in data folder.
    return error_page, 404, {'Content-Type': 'text/html'}

# Define own (async capable) decorator to check authorization
# Wrapped function MUST be a async function 
def authorize(func):
    async def wrapper(*args, **kwargs):
        try:
            # args[0] is the request object
            this_session = get_session( args[0] )
        except KeyError:
            this_session = {}
        # No need to check config.password_required because
        # that was checked when handing out the session cookie in after_request
        if this_session.get("login"):
            # Is login: authorized to call the function
            return await func(*args, **kwargs)
        # Not login: return 401 to force client to ask
        # for password.
        return respond_error_alert("Password required"), 401
    return wrapper


# Define (async capable) decorator to check if player is active
#
# Use @check_player_active for web functions that are likely 
# to be used during playback but can delay music while playing.
#
# Use @stop_playback for maintenance functions that
# will interfere with music playing and/or that require a reboot.
# @stop_playback will do a @check_player_active so music doesn't stop abruptly

def _player_decorator(func, stop_playback):
    async def wrapper(*args, **kwargs):
        # logger.async_info may delay response considerably, because it must wait
        # for a suitable time slot between MIDI events.
        if scheduler.is_player_active():
            _logger.async_info(f"Action not allowed while music player active: '{func.__name__}'")
            # Don't stop playback but skip webservice.
            return respond_error_alert(func.__name__), 403 # forbidden
        if stop_playback and setlist.stop_playback():
            # Music player not running. Can stop safely.
            # This message is shown only once
            _logger.async_info(f"Music playback stopped by: '{func.__name__}'")
        return await func(*args, **kwargs)
    return wrapper

# These are the actual decorators
# Don't allow function if player is active.
def check_player_active(func):
    return _player_decorator(func, False)

# If player is active: Don't allow 
# If player is not active: stop player
def stop_playback(func):
    return _player_decorator(func, True)

# Late-import organtuner, it saves lots of RAM if not needed.
# And when loaded, reboot is needed anyhow, so the impact is not relevant.
_organtuner_instance = None
def get_organtuner():
    # Load organ tuner late, only uses resources when needed
    global _organtuner_instance
    if not _organtuner_instance:
        from organtuner import OrganTuner
        _organtuner_instance = OrganTuner( gpio.microphone_pin )
    return _organtuner_instance
   



#
### File server
#
@app.route("/static/<filepath>")
async def ws_static_files(request, filepath):
    return await static_files( request, filepath )

async def static_files( request, path ):
    ua = request.headers.get("User-Agent")
    if ua:
        if "Chrome" not in ua and "Firefox" not in ua:
            # Could not make run Javascript's "await fetch" well in Safari.
            _logger.debug(f"Browser not supported {ua}")
            return "Safari not supported, use Chrome or Firefox"
    # No RequestSlice here, if someone wants to load pages while
    # playing music, let them.
    for folder in _STATIC_FOLDERS:
        filename = folder + path
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
            ct = fileops.get_mime_type( filename )

            return send_file(filename_zip, max_age=MAX_AGE, compressed=True, content_type=ct)
    _logger.info(f"static_files {filename} not found")
    return respond_not_found()


@app.route("/data/<filepath>")
async def send_data_file(request, filepath):
    filename = config.DATA_FOLDER + filepath
    # Do not serve non-existent files nor temporary MIDI files
    if not fileops.file_exists(filename) or filename.lower().endswith(".mid"):
        _logger.info(f"send_data_file {filename} not found")
        # Since a data file is requested (normally) by fetch_json() 
        # in Javascript, respond_not_found() will also
        # return a 404 error.
        return respond_not_found()
    # Don't cache data files with the brower. 
    # Cacheing json files is controlled at the Javascript level with the JsonCache class.

    return send_file(filename, max_age=0)


# Some browsers request favicon
def serve_favicon( fn ):
    for folder in _STATIC_FOLDERS:
        filename = folder + fn
        if fileops.file_exists( filename ):
            return send_file(filename, max_age=MAX_AGE)
    return respond_not_found() # ???

@app.route("/favicon.ico")
async def favicon_ico(request):
    return serve_favicon( "favicon.ico" )


@app.route("/favicon.png")
async def favicon_png(request):
    return serve_favicon( "favicon.png" )



#
### Authentication
#

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

# A very simple call just to ask for password and get authorized
@app.route("/get_permission")
@authorize
async def get_permission( request ):
    return {} 

# Not called from web page, used for debugging
@app.route("/logout")
async def logout(request): 
    get_session( request )["login"] = False
    return {}

#
### Common webservices
#
def get_progress():
    # Gather progress from all sources
    progress = player.get_progress()
    crank.complement_progress(progress)
    setlist.complement_progress(progress)
    # gpio has the RegisterBank() object
    gpio.get_registers().complement_progress(progress)
    tunemanager.complement_progress(progress)
    battery.complement_progress(progress)
    # commonGetProgress() in common.js filters for setlist and adds tunelib
    return progress


@app.route("/get_progress")
async def ws_get_progress(request):
    # get_progress() itself is very fast (<10 msec)
    return get_progress()


# Battery information web request, common to most pages, called from common.js
@app.route("/battery")
async def get_battery_status(request):
    return battery.get_info()


@app.post("/set_time_zone")
async def set_time_zone(request):
    # Set timezone, also may be setting time if not set yet
    await timezone.set_time_zone( request.json )
    # Respond with progress to let client know boot_session and tunelib signature
    return get_progress()
        
#
### Setlist management (play.html, tunelist.html, history.html)
#

@app.post("/queue_tune")
async def queue_tune(request):
    # Queue tune to setlist
    data = request.json
    setlist.queue_tune(data["tuneid"], data["slot"] )
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


@app.post("/save_setlist")
async def save_setlist(request):
    data = request.json
    setlist.save( data["slot"] )
    return get_progress()


@app.post("/load_setlist")
async def load_setlist(request):
    setlist.load( request.json["slot"] ) 
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

@app.route("/top_setlist/<tuneid>")
async def top_setlist(request, tuneid):
    setlist.top(tuneid)
    return get_progress()

@app.route("/bottom_setlist/<tuneid>")
async def bottom_setlist(request, tuneid):
    setlist.bottom(tuneid)
    return get_progress()


@app.route("/drop_setlist/<tuneid>")
async def drop_setlist(request, tuneid):
    setlist.drop(tuneid)
    return get_progress()


@app.route("/shuffle_set_list")
async def shuffle_set_list(request):
    setlist.shuffle()
    return get_progress()


@app.route("/shuffle_all_tunes")
async def shuffle_all_tunes(request):
    # Web page disables this button while playing
    # but if progress is slow, there may be a button clicked...
    async with scheduler.RequestSlice("shuffle_all_tunes", 200):
        setlist.shuffle_all_tunes()
    return get_progress()

@app.route("/shuffle_3stars")
async def shuffle_3stars(request):
    # Web page disables this button while playing
    # but if progress is slow, there may be a button clicked...
    async with scheduler.RequestSlice("shuffle_3stars", 200):
        setlist.shuffle_3stars()
    return get_progress()

@app.route("/get_setlist_titles")
async def get_setlist_titles( request ):
    # This get's cached
    return { "titles": setlist.get_titles() } 

@app.post("/save_setlist_titles")
async def save_titles( request ):
    setlist.save_titles( request.json )
    return respond_ok()


#
### Play.html page web services
#

@app.route("/set_velocity_relative/<int:change>")
async def set_velocity_relative(request, change):
    crank.set_velocity_relative(change)
    return get_progress()

@app.route("/tacho_irq_report")
def tacho_irq_report(request):
    return crank.td.irq_report()


@app.post( "/tempo_follows_crank" )
async def tempo_follows_crank( request ):
    data = request.json
    player.set_tempo_follows_crank( data["tempo_follows_crank"] )
    return get_progress()

@app.post( "/repeats_requested" )
async def request_repeats( request ):
    data = request.json
    player.change_repeats_requested( int(data["repeats_requested"]) )
    return get_progress()


@app.post( "/toggle_register")
async def toggle_register( request ):
    data = request.json
    reg = gpio.get_registers().factory( data["name"])
    reg.set_value(data["value"])
    return get_progress()

#
### Organ tuner web services (show tuning)
#
@app.route("/get_organtuner_json")
@check_player_active # allows the user to see tuning without stopping playback
async def get_organtuner_json( request ):
    return get_organtuner().get_organtuner_json();

@app.route("/get_tuning_stats")
@check_player_active # allows the user to see tuning without stopping playback
# If no "check_player_active" then a background page reload may interfere with music
async def get_tuning_stats(request):
    return get_organtuner().get_stats()  

#
### Organ tuner web services (do tuning)
#

@app.route("/tune_all")
@stop_playback
async def start_tune_all_notes(request):
    # All tuning requests (except clear_tuning)
    # just queue the operation and respond, so
    # it's not of interest to return organtuner.json
    # in these functions
    get_organtuner().tune_all()
    return respond_ok()


@app.route("/start_tuning/<int:pin_index>")
@stop_playback
async def start_tuning(request, pin_index):
    # Tune one note
    get_organtuner().queue_tuning(get_organtuner().wait, 1000 )
    get_organtuner().queue_tuning(get_organtuner().update_tuning, pin_index)
    return respond_ok()


@app.route("/sound_note/<int:pin_index>")
@stop_playback
async def sound_note(request, pin_index):
    get_organtuner().queue_tuning(get_organtuner().sound_note, pin_index)
    return respond_ok()


@app.post("/repeat_note")
@stop_playback
async def repeat_note(request):
    get_organtuner().queue_tuning(get_organtuner().repeat_note, request.json )
    return respond_ok()


@app.route("/scale_test")
@stop_playback
async def scale_test(request):
    get_organtuner().queue_tuning(get_organtuner().scale_test, 0)
    return respond_ok()

@app.route("/all_pin_test")
@stop_playback
async def all_pin_test(request):
    get_organtuner().queue_tuning(get_organtuner().all_pin_test, 0)
    return respond_ok()


@app.route("/clear_tuning")
@stop_playback
async def clear_tuning(request):
    get_organtuner().clear_tuning()
    return respond_ok()

@app.route("/stop_tuning")
async def stop_tuning(request):
    get_organtuner().stop_tuning()
    return respond_ok()

@app.route("/set_avg_frequency")
@stop_playback
async def set_avg_frequency(request):
    get_organtuner().set_avg_frequency()
    return respond_ok()


#
### Home page (index.html)
#

@app.route("/")
async def index_page(request):
    return redirect( "/static/index.html")

@app.route("/get_index_page_info")
async def get_index_page_info(request):
    return {"servernode": config.servernode}


@app.route("/battery_zero")
async def battery_zero(request):
    battery.set_to_zero()
    return battery.get_info()

@app.post("/record_battery_level")
async def record_battery_level(request):
    battery.record_level( request.json["level"]  )
    return battery.get_info()

#
### System information (diag.html)
#
@app.route("/errorlog")
async def errorlog(request):
    # Show current error log
    filename = _logger.get_current_log_filename() 
    # Must be encoded like encodeURIComponent()
    filename = filename.replace( "/", "%2F" )
    return redirect( "/show_file/" + filename )

@app.route("/diag")
@check_player_active
async def diag(request):
    gc.collect()
    t0 = ticks_ms()
    gc.collect()  # measure optimal gc.collect() time
    t1 = ticks_ms()
    gc_collect_time = ticks_diff(t1, t0)
    # mem_free and mem_alloc are quite slow, similar to gc.collect()
    free_ram = gc.mem_free()  
    used_ram = gc.mem_alloc() 
    # statvfs takes 1.5 sec
    vfs = os.statvfs("/")

    midi_files = tunemanager.get_tune_count()


    now = timezone.now_ymdhmsz()
    tz = timezone.get_time_zone_info()
    time_zone_info = f'{tz["longName"]}, {tz["shortName"]}, offset={round(-tz["offset"]/60.0)} min'
    reboot_sec = round(ticks_diff(ticks_ms(), config.BOOT_TICKS_MS) / 1000 )
    used_flash = vfs[0] * (vfs[2] - vfs[3])
    free_flash = vfs[0] * vfs[3]
    d = {
        "description": config.description,
        "name": config.name,
        "mp_version": os.uname().version,
        "mp_bin": sys.implementation._machine, # type:ignore
        "last_refresh": now,
        "time_zone_info":  time_zone_info,
        "reboot_mins": f"{reboot_sec//60}:{reboot_sec%60:02d}",
        "free_flash": free_flash,
        "used_flash": used_flash,
        "free_ram": free_ram,
        "used_ram": used_ram,
        "gc_collect_time": gc_collect_time,
        "max_gc_collect_time": scheduler.max_gc_time,
        "solenoid_devices": actuator_bank.get_pin_info("<br>"),
        "midi_files": midi_files,
        "tunelib_folder": config.TUNELIB_FOLDER,
        "logfilename": _logger.get_current_log_filename(),
        "errors_since_reboot": _logger.get_error_count(),
        "compile_date": compiledate,
        "crank_installed": crank.is_installed()
    }
    try:
        from mcserver import mcserver # type:ignore
        d["mcserver"] = mcserver.get_last_backup_time()
    except:
        d["mcserver"] = ""

    _logger.info(f"diag: {used_flash=:_} {free_flash=:_}  {used_ram=:_} {free_ram=:_} {gc_collect_time=} max gc={scheduler.max_gc_time} {midi_files=}")
    return d


@app.route("/reset")
async def reset_microcontroller(request):
    # Wait for web server to respond, wait for led to flash, etc
    # Don't shut down microdot, need it to respond
    asyncio.create_task( poweroff.wait_and_reset() )
    return respond_ok()


@app.route("/deep_sleep")
async def deep_sleep(request):
    asyncio.create_task(poweroff.wait_and_power_off())
    return respond_ok()


@app.route("/wifi_scan")
@check_player_active
async def wifi_scan(request):
    # Takes 3 seconds or more
    return wifimanager.sta_if_scan()
    

@app.route("/get_wifi_status")
# This is fast, no @check_player_active needed
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

#
### General configuration
#
@app.route("/get_current_config")
async def get_current_config(request):
    return config.get_current_config()

#
### General configuration (changes)
#
# It's ok to show config during playback... but only show.
@app.route("/get_stored_config")
async def get_stored_config(request):
    return config.get_stored_config()


@app.post("/save_config")
@authorize
async def save_config(request):
    # Better use RequestSlice than check_player_active,
    # to ensure config can be changed even with automatic playback
    # and debug crank options
    async with scheduler.RequestSlice("save_config", 200):
        config.save(request.json)
    return respond_ok()

#
### Pinout and MIDI Configuration
#
cached_plist = None
def get_pinout_list():
    global cached_plist
    if not cached_plist:
        from pinoutweb import PinoutList
        cached_plist = PinoutList(  config.PINOUT_FOLDER, config.PINOUT_TXT )
    return cached_plist

@app.route("/pinout_list")
@check_player_active
async def pinout_list(request):
    plist = get_pinout_list()
    return plist.get_filenames_descriptions()

@app.route("/get_pinout_filename")
@check_player_active
async def get_pinout_filename(request):
    plist = get_pinout_list()
    return {
        "pinout_filename": plist.get_saved_pinout_filename(),
        "pinout_description": plist.get_description(),
    }

@app.route("/get_used_pins/<path>")
@check_player_active
async def get_used_pins( request, path ):
    from pinoutweb import GPIOstatistics
    # Let user do this while player is active
    return GPIOstatistics(decodePath(path), False).get_used_pins()

@app.post("/save_pinout_filename")
@authorize
@stop_playback
async def save_pinout_filename(request):
    # Force reboot to make this take effect.
    data = request.json
    plist = get_pinout_list()
    plist.set_current_pinout_filename(data["pinout_filename"])

    return respond_ok()


@app.post("/save_pinout_detail/<path>")
@authorize
@stop_playback
async def save_pinout_detail(request, path):
    # Force reboot to use the player to make definitions take effect.
    # However, it's not mandatory to stop current tune and setlist,
    # unlike organtuner.
    output_filename = decodePath(path)
    try:
        # SaveNewPinout class will validate and do a init of pint
        # Raise error if pinout is not valid
        from pinoutweb import SaveNewPinout
        SaveNewPinout(output_filename, request.json, True)
        _logger.debug("save_pinout_detail pinout.save complete")
        return respond_ok()
    except RuntimeError as e:
        _logger.debug(f"save_pinout_detail exception {repr(e)}")
        return respond_error_alert(f"pinout not saved: {repr(e)}")


@app.route("/list_pinout_by_midi_note/<path>")
@check_player_active
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
    # loaded. The result of parsing here is deleted when exiting
    # list_midi_note.
    actuator_def = ActuatorDef( RegisterBank(), filename, False) 
    controller = actuator_def.get_controller()
    notedef = []
    for midi_note, action in controller.get_notedict().items():
        for _, _, reg, actuator in action:
            notedef.append( {  
                             "program_number":midi_note.program_number, 
                             "midi_number":midi_note.midi_number, 
                             "midi_note": str(midi_note), 
                             "actuator_name": str(actuator), 
                             "actuator_note": str(actuator.nominal_midi_note) if actuator.nominal_midi_note else "", 
                             "actuator_rank": actuator.get_rank_name(), 
                             "register_name": reg.name,
                             "invert": False } )
        #for actuator in action:
        #    notedef.append( {
        #                      "program_number":actuator.nominal_midi_note.program_number, 
        #                      "midi_number":actuator.nominal_midi_note.midi_number, 
        #                      "midi_note": str(actuator.nominal_midi_note), 
        #                      "actuator_name": str(actuator), 
        #                      "actuator_note": str(actuator.nominal_midi_note) if actuator.nominal_midi_note else "", 
        #                      "actuator_rank": actuator.get_rank_name(), 
        #                      "register_name": "",
        #                      "invert": False } )
    notedef.sort( key=sort_key )
                
    return notedef


@app.post("/test_pin")
@stop_playback
async def test_pin( request ):
    alert_message = await PinTest.web_test_pin( request.json, actuator_bank )
    if alert_message:
        return respond_error_alert( alert_message )
    return respond_ok()
    
@app.post("/scan_i2c")
@stop_playback
async def scan_i2c( request ):
    return {"scan":PinTest.scan_i2c( request.json )}

@app.route("/tacho_raw_value")
@stop_playback
def tacho_raw_value(request):
    # >>> test is done with saved pin, not latest value. Show pins? hide test?
    return {"value": crank.td.raw_value() }

@app.route("/test_mic/<pin>")
@stop_playback
async def test_mic(request, pin):
    try:
        from microphone import Microphone
        mic = Microphone( int(pin), False )
    except:
        # pin cannot be used, example: no ADC pin.
        # pin not numeric
        # pin number out of range
        return  respond_error_alert( f"Invalid pin: {pin}")
    gpiotest = PinTest.testGPIO( int(pin) )
    duration, signal = mic.sample_microphone( NoteDef(0,95) )
    return {"signal": list(signal), "duration": duration, "gpiotest": gpiotest }

@app.post("/test_touchpad")
@stop_playback
async def test_touchpad( request ):
    data = request.json
    try:
        from startbase import startButtonFactory
        button = startButtonFactory( int(data["pin"]), int(data["technology"]) )
    except Exception as e:
        return respond_error_alert( f"Invalid touchpad {data}: {e}")
    return {"value": button.read() }


#
### Faux drum support
#

@app.post("/test_drumdef")
async def test_drumdef( request ):
    # Drum definition does not stop playback, it's desirable
    # to use a MIDI to see how it works.
    # Reflect changes in web form to memory, taking effect immediately
    from driver_ftoms import FauxTomDriver
    drumdef = request.json
    for pin in FauxTomDriver.get_pin_list():
        dd = drumdef[str(pin.nominal_midi_number)]
        pin.set_virtual_drum_characteristics( dd )
    return respond_ok()

@app.post("/save_drumdef")
async def save_drumdef( request ):
    # Don't disable music playback here, need to play
    # MIDI while testing drums.
    from driver_ftoms import FauxTomDriver
    FauxTomDriver.save( request.json )
    return respond_ok()

#
### Tunelib editor
#
@app.route("/start_tunelib_sync")
@stop_playback
async def start_tunelib_sync(request):
    # User pressed "sync all" button
    # Stop playback will show prominently that no music can play back
    # because sync interferes
    tunemanager.start_sync()
    return respond_ok()


@app.route("/tunelib_sync_progress")
async def tunelib_sync_progress(request):
    return {"progress": tunemanager.get_sync_progress()}

@app.post("/queue_field_changes")
async def queue_field_changes(request):
    # Queuing is acceptably fast, no need to restrict much
    async with scheduler.RequestSlice("queue_field_changes", 300):
        tunemanager.queue_field_changes(request.json)
    return respond_ok()

@app.post("/save_lyrics")
@stop_playback
async def save_lyrics( request ): 
    data = request.json
    tunemanager.save_lyrics( data["tuneid"], data["lyrics"])
    return respond_ok()

#
### History page
#
@app.route("/delete_history/<int:days>")
@check_player_active
async def delete_history(request, days):
    history.delete_old(days)
    return respond_ok()

@app.route("/delete_history_date/<date>")
@check_player_active
async def delete_history_date(request, date):
    history.delete_date(date)
    return respond_ok()


#
### File manager
#

def decodePath( path ):
    # Inverse function to encodePath() in common.js
    return urldecode_bytes( path.encode() )

@app.route("/listdir")
@app.route("/listdir/")
@app.route("/listdir/<path>")
@check_player_active
async def filemanager_listdir(request, path=""):
    # >>> check_player_active may depend on path? 
    listpath = decodePath(path)
    if listpath.endswith("filemanager.html"):
        # Don't navigate to /static/filemanager.html please.
        return respond_error_alert("Use /filemanager")
    import filemanager
    return filemanager.listdir( listpath )

@app.post("/upload/<path_filename>")
@authorize 
@check_player_active
async def filemanager_upload(request, path_filename ):
    path, filename, mtime, size = path_filename.split("+")
    path = decodePath( path )
    filename = decodePath( filename )
    import filemanager
    try:
        r =  filemanager.upload( request.body, path, filename, int(mtime), int(size)  )
        op = "Updating"
        if r["skip"]:
            op = "Skipping"
        elif r["oldFileSize"] == None:
            op = "Creating"
        _logger.info(f"{op} {filename} to {path} size={ r['oldFileSize']}->{r['newFileSize']} bytes")
        return r
    except Exception as e:
        _logger.exc( e, "In /upload")
        return respond_error_alert(f"Error uploading {repr(e)}")
    
@app.route("/download/<path>")
@authorize
@check_player_active
async def filemanager_download(request, path):
    # Download a file from the microcontroller to the PC
    import filemanager
    return filemanager.download( decodePath( path ) )

@app.route("/show_file/<path>")
# THis is used on the diag page for error log. Allow usage without @check_player_active
async def filemanager_show_file( request, path ):
    import filemanager
    try:
        return filemanager.show_file( decodePath( path ) ) 
    except OSError as e:
        return respond_error_alert(f"File not found: {e}")

@app.route("/used_flash")
@check_player_active
async def filemanager_status(request):
    import filemanager
    return filemanager.status()

@app.post("/delete_file")
@authorize
@check_player_active
async def filemanager_delete(request):
    # Delete a file
    path = request.json["delete_filename"]
    # No need to urldecode this, filename was posted in json.
    import filemanager
    try:
        filemanager.delete( path  )
    except Exception as e:
        # Can happen if there are 2 browser windows
        _logger.error(f"Error deleting file {path}: {e}")
        return respond_error_alert(f"Error {e} deleting file {path}")
    return respond_ok()


# Test: tarball with 608 files, 3_021_365 bytes net, 4_292_608 bytes on flash
# took 133.8 sec (2 minutes and 14 seconds) 
# and output file was 3_491_840 bytes on flash.
@app.post("/make_tarball")
@authorize
@check_player_active
async def make_tarball(request):
    import filemanager
    # The request.json has the list of microcontroller files to be added to the tarball.
    return filemanager.make_tarball( request.json )


@app.route("/filemanager")
@app.route("/filemanager/")
@app.route("/filemanager/<path>")
async def handle_filemanager( request, path=""):
    # Load page, javascript will retrieve the path an call back
    return await static_files( request, "filemanager.html" )

#
### Catchall and error handler
#
#
#  Catchall handler to debug possible errors at html level
@app.get("/<path:path>")
async def catch_all(request, path):
    _logger.debug(f"***CATCHALL*** {path=}")
    return respond_not_found()

@app.errorhandler(RuntimeError) # "(errorhandler)"
async def runtime_error(request, exception):
    return respond_error_alert("RuntimeError exception detected")

# >>> check http error 400 on filemanager upload from a cell phone local file???

# >>> this error stops the complete application, is raised to
# >>>  the global asyncio error handler (occurred only once in
# during a test situation when changing the WiFi router.
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
    global _logger, MAX_AGE

    # Configure file cache for browser
    # MAX_AGE is applied selectively
    _logger.debug(f"{MAX_AGE=:,} sec {_STATIC_FOLDERS=}")
    await app.start_server(host="0.0.0.0", port=80 )

# Not used
# async def shutdown():
#     app.shutdown()
