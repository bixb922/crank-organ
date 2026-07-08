from random import getrandbits

_CANCELLED = const("cancelled") 
_ENDED = const("ended")
_PLAYING = const("playing")

_boot_session =  hex(getrandbits(24))
_progress =  {"tune": None, "playtime": 0, "status": ""}
_callbacks = []


def tune_started(tuneid):
    global _progress
    _progress = {"tune": tuneid, "playtime": 0, "status": _PLAYING}

def tune_ended():
    _progress["status"] = _ENDED

def tune_cancelled():
    global _progress
    _progress = {"tune": None, "playtime": 0, "status": _CANCELLED}

def report_exception(message):
    _progress["status"] = message

def register_callback( cb ):
    _callbacks.append( cb )

def get():
    for cb in _callbacks:
        cb(_progress)
    _progress["boot_session"] = _boot_session
    return _progress

