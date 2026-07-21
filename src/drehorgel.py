# Copyright (c) 2025 Hermann von Borries
# MIT license

# Led, timezone and config are initialized before
# the rest:
#   led is turned on ASAP
#   create folders so that it's not necessary to check if folders are not there
#   timezone is needed for minilog
#   minilog is needed for most modules
#

def init_led():
    global led
    from led import BlinkingLed
    led = BlinkingLed()
    return led

def init_fileops():
    import fileops
    # If installed from romfs and no data folder,
    # then create folder and populate initial data files
    if not fileops.folder_exists("/data"):
        # Call install_data only if data folder does not exist yet,
        # i.e. only once just after flashing the firmware.
        try:
            # install_data.py is a self extractable file on ROMFS
            # with initial data files. Importing it installs the files.
            # install_data.py may be present in romfs
            # Do not allocate variable, so memory is freed.
            __import__("install_data") 

        except ImportError:
            fileops.make_folder( "/data")

    fileops.make_folder( "/tunelib")
    # /software/mpy and /software/static only get created when
    # uploading software (Python/HTML/Javascript)

def init_timezone():

    from timezone import TimeZone
    global timezone
    timezone = TimeZone()

    # inject timezone and logger mutually
    from minilog import getLogger
    getLogger.set_timezone( timezone )
    timezone.set_logger( getLogger )

def init_config():
    from config import Config
    global config
    config = Config( True )

    # Inject configuration to getLogger.
    from minilog import getLogger
    getLogger.set_file_level( config.log_debug )

async def init_wifimanager():

    from wifimanager import WiFiManager
    global wifimanager
    wifimanager = WiFiManager()
    await wifimanager.async_init()

def init_pinout():

    global gpio, controller, actuator_bank
    
    led.starting(1)

      # Get list of pinout.json files
    from pinout import GPIODef, ActuatorDef, get_current_pinout
    current_pinout_file = get_current_pinout( config.PINOUT_TXT )
    
    # Parse definitions for GPIO ports except GPIO MIDI ports
    # but including registers
    gpio = GPIODef( current_pinout_file, False )
    
    # Parse actuator definitions: GPIO/MCP23017/MIDI Serial and
    # all midi elements in the pinout.json
    from solenoid import ActuatorBank
    actuator_def = ActuatorDef( gpio.get_registers(), current_pinout_file, False )# It's not necessary to store actuator_def
    
    actuator_bank = ActuatorBank( 
        actuator_def,
        config )

    # Remember the MIDI controller,
    # many friends like to know her/him.
    controller = actuator_def.get_controller()
    
    # The controller has to be able to act on all actuators
    controller.define_complete( actuator_bank )

    del actuator_def

def init_modules():

    global history, player, setlist, crank, tunemanager
    global battery, poweroff, tempo_encoder

    led.starting(2)
 
    # Player/setlist need to know if crank is turning.
    from tachometer import Crank
    crank = Crank(gpio.tachometer_pin1, gpio.tachometer_pin2 )
    # The rotary tempo encoder operates as a independent task
    tempo_encoder = None
    if gpio.tempo_a and gpio.tempo_b:
        from rotary import TempoEncoder # late import, so it will not use RAM if not referenced in pinout.json
        tempo_encoder = TempoEncoder( crank, gpio.tempo_a, gpio.tempo_b, gpio.tempo_switch, config.rotary_tempo_mult )
        # global variable tempo_encoder is currently not in use.

    from history import HistoryManager
    # Need to create empty history file if not there.
    history = HistoryManager()

    from battery import Battery
    battery = Battery()
    
    from tunemanager import TuneManager
    tunemanager = TuneManager()
    
    from player import MIDIPlayer
    player = MIDIPlayer()

    from setlist import Setlist
    setlist = Setlist()

    from poweroff import PowerManager
    poweroff = PowerManager()
 




