# Copyright (c) 2025 Hermann von Borries
# MIT license

# Led, timezone and config are initialized before
# the rest:
#   led should be turned on ASAP
#   timezone is needed for minilog, and minilog
#   is needed for most modules
#

def init_led():
    global led
    from led import BlinkingLed
    led = BlinkingLed()

def init_fileops():
    import fileops
    # If installed from romfs and no data folder,
    # then create folder and populate initial data files
    if not fileops.folder_exists("/data"):
        try:
            # install_data.py is a self extractable file on ROMFS
            # with initial data files. Importing it installs the files.
            # install_data.py may be present in romfs
            import install_data # type: ignore
        except ImportError:
            fileops.make_folder( "/data")

    fileops.make_folder( "/tunelib")
    # /software/mpy and /software/static only get created when
    # uploading software (Python/HTML/Javascript)

def init_timezone():
    from timezone import TimeZone
    global timezone
    timezone = TimeZone()

def init_config():
    from config import Config

    global config
    config = Config( True )

    # Inject configurations where needed due to mutual dependencies
    from minilog import getLogger
    getLogger.set_file_level( config.log_debug )

async def init_wifimanager():
    from wifimanager import WiFiManager
    global wifimanager
    wifimanager = WiFiManager()
    await wifimanager.async_init()

def init():
    global history, player, setlist, crank, tunemanager
    global plist, gpio, controller, actuator_bank
    global battery, poweroff
    # global tempo_encoder
    
    led.starting(1)

      # Get list of pinout.json files
    from pinout import PinoutList, GPIODef, ActuatorDef
    plist = PinoutList(config.PINOUT_TXT, config.PINOUT_FOLDER)
    current_pinout_file = plist.get_current_pinout_filename()
    
    # Parse definitions for GPIO ports except GPIO MIDI ports
    # but including registers
    gpio = GPIODef( current_pinout_file )
    
    # Parse actuator definitions: GPIO/MCP23017/MIDI Serial and
    # all midi elements in the pinout.json
    from solenoid import ActuatorBank
    actuator_def = ActuatorDef( current_pinout_file, gpio.get_registers()) # It's not necessary to store actuator_def
    actuator_bank = ActuatorBank( 
        actuator_def,
        config )
    
    # Remember the MIDI controller,
    # many friends like to know her/him.
    controller = actuator_def.get_controller()
    
    # The controller has to be able to act on all actuators
    controller.define_complete( actuator_bank )
    
    del actuator_def
    
    led.starting(2)
 
    # Player/setlist need to know if crank is turning.
    from tachometer import Crank
    crank = Crank(gpio.tachometer_pin1, gpio.tachometer_pin2 )
    
    # The tempo encoder operates as a independent task,
    # >>>tempo encoder not of interest?
    #  = None
    # if gpio.tempo_a and gpio.tempo_b:
    #    tempo_encoder = TempoEncoder( crank, gpio.tempo_a, gpio.tempo_b, gpio.tempo_switch, config.rotary_tempo_mult )
        
    from history import HistoryManager
    # Need to create empty history file if not there.
    history = HistoryManager()

    from battery import Battery
    battery = Battery()
    
    from tunemanager import TuneManager
    tunemanager = TuneManager(config.TUNELIB_FOLDER, config.TUNELIB_JSON, config.LYRICS_JSON, config.SYNC_TUNELIB )
    
    from player import MIDIPlayer
    player = MIDIPlayer()

    from setlist import Setlist
    setlist = Setlist()

    from poweroff import PowerManager
    poweroff = PowerManager()
 





