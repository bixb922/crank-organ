# (c) 2023 Hermann Paul von Borries
# MIT License
# Webserver module, serves all http requests.

# >>> titulo de pagina = nombre dispositivo
import os
import sys
import gc
import asyncio
import time
import ubinascii

from microdot_asyncio import Microdot, send_file, redirect

from minilog import getLogger
import scheduler
from config import config, password_manager
import pinout
from battery import battery
from wifimanager import wifimanager
from solenoid import solenoid
from compiledate import compiledate

from tunemanager import tunemanager
import tachometer

from setlist import setlist
from history import history
from timezone import timezone
from player import player
from organtuner import organtuner
import fileops
from poweroff import poweroff
from led import led

# Testing needed
# import soleble

app = Microdot()

USE_CACHE = True  # will be set by run_webserver() to value in config.json
MAX_AGE = (
    24 * 60 * 60
)  # Pages are in cache for 1 day. Will be set to 0 of no cache


# index.html, tunelist.html, play.html: enable play mode
# notelist.html note.html, pinout.html: disable play mode
# tunelibedit, diag, history, config: no change

PAGE_ENABLES_PLAYBACK = {
    "index.html": True,
    "tunelist.html": True,
    "play.html": True,
    "notelist.html": False,
    "note.html": False,
    "pinout.html": False,
    # Rest of pages are neutral wr to playback
}

# @app.before_request
# def func_before_req( request ):
#    pass


# @app.after_request
# def func_after_req( response ):
#    dt = time.ticks_diff( time.ticks_ms(), r.g.t0 )
#    print(f"request ended  {r.method=} {r.url=} {dt} msec")
#    return response


def _file_exists(filename):
    try:
        os.stat(filename)
        return True
    except OSError:
        return False


# Information active clients
# key=client IP, data=time.ticks_ms()) of last activity
client_activity = {}


def register_activity(request):
    client_activity[request.client_addr[0]] = time.ticks_ms()


def is_active(since_seconds=60):
    # This is used by poweroff.py
    try:
        t = time.ticks_diff(
            time.ticks_ms(), min(list(client_activity.values()))
        )
        # Return true if recent activity
        return t < since_seconds * 1000
    except ValueError:
        # no client activity, empty list
        pass
    return False


def simple_response(message, k=None, v=None):
    if message == "ok":
        resp = {"result": "ok"}
    else:
        resp = {"alert": message}
    if k:
        resp[k] = v
    return resp


def check_authorization(request):
    if not config.cfg["password_required"]:
        return
    name = config.cfg["name"]
    # >>>> CHECK USERNAME==NAME???
    ask_for_password = ({}, 401, {"WWW-Authenticate": f'Basic realm="{name}"'})
    # This will prompt a "basic authentication" dialog, asking for username/password
    # on the browser side. In case of password error, the browser will retry on its own
    # sending username/password in the Authorization header.
    # @app.route, must have
    # save_headers=["Content-Length","Content-Type","Authorization"])
    auth = request.headers.get("Authorization", "")
    if not auth:
        # No authorization header present, responde with
        # http 401 error "not authorized" to ask for password
        return ask_for_password

    # Authorization header expected to be "Basic xxxxxx", xxx is base64 of username/password
    basic, userpass = auth.split(" ")
    assert basic == "Basic", f"Basic authentication expected, got {basic}"
    # base64 information is "user:password"
    user, password = ubinascii.a2b_base64(userpass.encode()).decode().split(":")
    if not password_manager.verify_password(password):
        _logger.info("Web access not authorized: incorrect password")
        return ask_for_password
    # Authenticated
    return


# Home page
@app.route("/")
async def index_page(request):
    inipage = "/static/" + config.cfg.get("initial_page", "index") + ".html"
    return redirect(inipage)


# File related web requests
@app.route("/static/<filepath>")
async def static_files(request, filepath):
    ua = request.headers.get("User-Agent")
    if ua:
        if "Chrome" not in ua and "Firefox" not in ua:
            # Could not make run Javascript await fetch in Safari.
            _logger.debug(f"Browser not supported {ua}")

            return "Safari not supported, use Chrome or Firefox"

    register_activity(request)

    # Playback mode depends on page last loaded
    pb = PAGE_ENABLES_PLAYBACK.get(filepath, None)
    if pb is not None:
        scheduler.set_playback_mode(pb)
    filename = STATIC_FOLDER + filepath
    if not fileops.file_exists(filename):
        return "", 404

    return send_file(filename, max_age=MAX_AGE)


@app.route("/data/<filepath>")
async def send_data_file(request, filepath):
    if "config" in filepath:
        # Config.json and it's backups not visible this way.
        return {}, 404

    register_activity(request)
    filename = DATA_FOLDER + filepath
    if not fileops.file_exists(filename):
        return "", 404

    return send_file(filename, max_age=0)


def get_progress(request):
    register_activity(request)
    progress = player.get_progress()
    tachometer.complement_progress(progress)
    scheduler.complement_progress(progress)
    setlist.complement_progress(progress)

    return progress


@app.route("/get_progress")
async def process_get_progress(request):
    return get_progress(request)


@app.route("/queue_tune/<tune>", methods=["GET", "POST"])
async def queue_tune(request, tune):
    # Queue tune to setlist
    setlist.queue_tune(tune)
    # Wait for setlist process to catch up
    # await asyncio.sleep_ms( 500 )
    # return get_progress( request )
    return get_progress(request)


@app.route("/start_tune")
async def go_tempo(request):
    setlist.start_tune()
    return get_progress(request)


@app.route("/stop_tune_setlist")
async def stop_tune_setlist(request):
    setlist.stop_tune()
    return get_progress(request)


@app.route("/back_setlist")
async def back_setlist(request):
    setlist.to_beginning_of_tune()
    return get_progress(request)


@app.route("/save_setlist")
async def save_setlist(request):
    setlist.save()
    return simple_response("ok")


@app.route("/load_setlist")
async def load_setlist(request):
    setlist.load()
    return get_progress(request)


@app.route("/clear_setlist")
async def clear_setlist(request):
    setlist.clear()
    return get_progress(request)


@app.route("/up_setlist/<int:pos>")
async def up_setlist(request, pos):
    setlist.up(pos)
    return get_progress(request)


@app.route("/down_setlist/<int:pos>")
async def down_setlist(request, pos):
    setlist.down(pos)
    return get_progress(request)


@app.route("/shuffle_set_list")
async def shuffle_set_list(request):
    setlist.shuffle()
    return get_progress(request)


@app.route("/shuffle_all_tunes")
async def shuffle_all_tunes(request):
    setlist.shuffle_all_tunes()
    return get_progress(request)


# Organ tuner web requests


@app.route("/note/<int:midi_note>")
async def note_page(request, midi_note):
    return send_file(STATIC_FOLDER + "note.html", max_age=MAX_AGE)


@app.route("/tune_all")
async def start_tune_all(request):
    # All tuning requests (except clear_tuning)
    # just queue the operation and respond, so
    # it's not of interest to return organtuner.json
    # in these functions
    organtuner.tune_all()
    return simple_response("ok")


@app.route("/start_tuning/<int:midi_note>")
async def start_tuning(request, midi_note):
    # Tune one note
    organtuner.queue_tuning(("tune", midi_note))
    return simple_response("ok")


@app.route("/sound_note/<int:midi_note>")
async def sound_note(request, midi_note):
    organtuner.queue_tuning(("note_on", midi_note))
    return simple_response("ok")


@app.route("/sound_repetition/<int:midi_note>")
async def sound_repetition(request, midi_note):
    organtuner.queue_tuning(("note_repeat", midi_note))
    return simple_response("ok")


@app.route("/scale_test")
async def scale_test(request):
    organtuner.queue_tuning(("scale_test", 0))
    return simple_response("ok")


@app.route("/clear_tuning")
async def clear_tuning(request):
    organtuner.clear_tuning()
    return send_file(config.ORGANTUNER_JSON)


@app.route("/stop_tuning")
async def stop_tuning(request):
    organtuner.stop_tuning()
    return simple_response("ok")


# Battery information web request, common to most pages, called from common.js
@app.route("/battery")
async def get_battery_status(request):
    # When playing music, /battery is good indicator of activity
    register_activity(request)
    return battery.get_info()


# Index.html page web requests


@app.route("/battery_zero")
async def battery_zero(request):
    battery.set_to_zero()
    return battery.get_info()


@app.route("/errorlog")
async def show_log(request):
    def log_generator():
        # Format log as HTML, only last log is shown.
        with open(_logger.get_current_log_filename()) as file:
            yield "<!DOCTYPE html><head></head><body><title>Error log</title><body><table>"
            while True:
                s = file.readline()
                if s == "":
                    break
                if s[0:1] == " ":
                    # This happens for exception traceback, put traceback info in column 3
                    yield (
                        "<tr><td></td><td></td><td></td><td>" + s + "</td></tr>"
                    )
                else:
                    yield "<tr>"
                    for p in s.split(" - "):
                        yield "<td>" + p + "</td>"
                    yield "</tr>"
        yield "</table></body>"

    return log_generator(), 200, {"Content-Type": "text/html; charset=UTF-8"}


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

    reboot_mins = (
        time.ticks_diff(time.ticks_ms(), config.boot_ticks_ms) / 1000 / 60
    )
    d = {
        "description": config.cfg["description"],
        "name": config.cfg["name"],
        "mp_version": os.uname().version,
        "mp_bin": sys.implementation._machine,
        "last_refresh": now,
        "reboot_mins": reboot_mins,
        "free_flash": vfs[0] * vfs[3],
        "used_flash": vfs[0] * (vfs[2] - vfs[3]),
        "free_ram": free_ram,
        "used_ram": used_ram,
        "gc_collect_time": gc_collect_time,
        "solenoid_devices": solenoid.get_status(),
        "midi_files": midi_files,
        "music_folder": config.MUSIC_FOLDER,
        "logfilename": _logger.get_current_log_filename(),
        "errors_since_reboot": _logger.get_error_count(),
        "compile_date": compiledate,
    }
    return d


@app.route("/reset")
async def reset_microcontroller(request):
    led.ack()
    asyncio.create_task(poweroff.wait_and_reset())
    return simple_response("ok")


@app.route("/deep_sleep")
async def deep_sleep(request):
    led.ack()
    asyncio.create_task(poweroff.wait_and_power_off())
    return simple_response("ok")


@app.route("/wifi_scan")
async def wifi_scan(request):
    return wifimanager.sta_if_scan()


@app.route("/get_wifi_status")
async def get_wifi_status(request):
    register_activity(request)
    c = wifimanager.get_status()
    now = time.ticks_ms()
    c["client_IPs"] = "".join(
        [
            ip + " "
            for ip in client_activity
            if time.ticks_diff(now, client_activity[ip]) < 10_000
        ]
    )
    return c


# Play page web requests
@app.route("/set_velocity/<int:vel>")
async def set_velocity(request, vel):
    tachometer.set_velocity(vel)
    return get_progress(request)


@app.route("/top_setlist/<int:pos>")
async def top_setlist(request, pos):
    setlist.top(pos)
    return get_progress(request)


@app.route("/drop_setlist/<int:pos>")
async def drop_setlist(request, pos):
    setlist.drop(pos)
    return get_progress(request)


# Configuration change


@app.route("/get_config")
async def get_config(request):
    return config.get_config()


@app.post("/save_config")
async def change_config(request):
    if response := check_authorization(request):
        return response

    resp = config.save(request.json)
    return simple_response(resp)


@app.route("/start_ftp")
async def start_ftp(request):
    if response := check_authorization(request):
        return response
    poweroff.cancel_power_off()
    scheduler.set_playback_mode(False)

    # Run FTP in a separate thread
    import _thread

    def uftpd_in_a_thread():
        import uftpd

        _logger.info("uftp started")

    _thread.start_new_thread(uftpd_in_a_thread, ())

    return simple_response("ok")


# Pinout functions
@app.route("/pinout_list")
async def pinout_list(request):
    return pinout.plist.get_filenames_descriptions()


@app.route("/pinout_detail")
async def pinout_detail(request):
    filename = pinout.plist.get_current_pinout_filename()
    return send_file(filename)


@app.route("/get_pinout_filename")
async def get_pinout_filename(request):
    resp = {
        "pinout_filename": pinout.plist.get_current_pinout_filename(),
        "pinout_description": pinout.plist.get_description(),
    }
    return resp


@app.route("/get_index_page_info")
async def get_index_page_info(request):
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
async def save_pinout_filename(request):
    if response := check_authorization(request):
        return response
    data = request.json

    pinout.plist.set_current_pinout_filename(data["pinout_filename"])
    solenoid.init_pinout()
    organtuner.clear_tuning()

    # Organtuner be aware: organtuner.json may no longer
    # be valid
    organtuner.pinout_changed()
    return simple_response("ok")


@app.post("/save_pinout_detail")
async def save_pinout_detail(request):
    if response := check_authorization(request):
        return response
    try:
        pinout.SaveNewPinout(request.json)
        solenoid.init_pinout()
        organtuner.clear_tuning()
        _logger.debug("save_pinout_detail pinoupt.save complete")
        return simple_response("ok")
    except RuntimeError as e:
        _logger.debug(f"save_pinout_detail exception {e}")
        return simple_response(f"pinout not saved: {e}")


@app.post("/test_mcp")
async def test_mcp(request):
    data = request.json
    await pinout.test.web_test_mcp(
        int(data["sda"]),
        int(data["scl"]),
        int(data["mcpaddr"]),
        int(data["pin"]),
    )
    return simple_response("ok")


@app.route("/test_gpio")
async def test_gpio(request):
    data = request.json
    await pinout.test.web_test_gpio(int(data["pin"]))
    return simple_response("ok")


# Generic requests requests: some browsers request favicon
@app.route("/favicon.ico")
async def serve_favicon(request):
    return send_file(STATIC_FOLDER + "favicon.ico", max_age=MAX_AGE)


@app.route("/favicon.png")
async def static_favicon(request):
    return send_file(STATIC_FOLDER + "favicon.png", max_age=MAX_AGE)


@app.route("/revoke_credentials")
async def revoke_credentials(request):
    return {}, 401


# Tunelib editor
@app.route("/start_tunelib_sync")
async def start_tunelib_sync(request):
    tunemanager.start_sync()
    return simple_response("ok")


# Tunelib editor
@app.route("/tunelib_sync_progress")
async def tunelib_sync_progress(request):
    progress = tunemanager.sync_progress()
    return simple_response("ok", k="progress", v=progress)


#
# Tunelib editor
@app.post("/save_tunelib")
async def save_tunelib(request):
    if response := check_authorization(request):
        return response

    tunemanager.save(request.json)
    return simple_response("ok")


@app.route("/get_history")
async def get_history(request):
    h = tunemanager.get_history()
    return h


@app.route("/delete_history/<int:months>")
async def delete_history(request, months):
    history.delete_old(months)
    return simple_response("ok")


# NO CATCHALL HANDLER FOR NOW


@app.errorhandler(RuntimeError)
def runtime_error(request, exception):
    return simple_response("RuntimeError exception detected")


async def run_webserver():
    global _logger, USE_CACHE, MAX_AGE
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
        MAX_AGE = config.get_int("max_age", 24 * 60 * 60)

    _logger.debug(f"{USE_CACHE=} {MAX_AGE=:,} sec")
    await app.start_server(host="0.0.0.0", port=80, debug=False)


async def shutdown():
    await app.shutdown()
