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
    fileops.make_folder( "/data")
    # >>> move this to frequency.py where /signals was defined
    fileops.make_folder( "/signals" )
    fileops.make_folder( "/tunelib")

def init_timezone():
    from timezone import TimeZone
    global timezone
    timezone = TimeZone()

def init_config():
    from config import  Config

    global config
    config = Config(  )
    
async def init_wifimanager():
    from wifimanager import WiFiManager
    global wifimanager
    wifimanager = WiFiManager()
    await wifimanager.async_init()

def init():
    global history, player, setlist, crank, tempo_encoder, tunemanager
    global plist, gpio, controller, actuator_bank
    global battery
    global organtuner
    global microphone, poweroff, battery
    global run_webserver

    led.starting(1)

      # Get lis of pinout.json files
    from pinout import PinoutList, GPIODef, ActuatorDef
    plist = PinoutList(config.PINOUT_TXT, config.PINOUT_FOLDER)
    current_pinout_file = plist.get_current_pinout_filename()
    
    # Parse definitions for GPIO ports except GPIO MIDI ports
    # but including registers
    gpio = GPIODef( current_pinout_file )
    
    # Parse actuator definitions: GPIO/MCP23017/MIDI Serial and
    # all midi elements in the pinout.json
    actuator_def = ActuatorDef( current_pinout_file, gpio.get_registers()) # It's not necessary to store actuator_def

    from solenoid import ActuatorBank
    actuator_bank = ActuatorBank( 
        config.cfg.get("max_polyphony",10), 
        actuator_def )

    # Remember the MIDI controller,
    # many friends like to know her/him.
    controller = actuator_def.get_controller()
    
    # The controller has to be able to act on all actuators
    controller.define_complete( actuator_bank )
    
    
    led.starting(2)
 
    # Player/setlist need to know if crank is turning.
    from tachometer import Crank, TempoEncoder
    crank = Crank(gpio.tachometer_pin1, gpio.tachometer_pin2 )
    # The tempo encoder operates as a independent task,
    tempo_encoder = TempoEncoder( crank,gpio.tempo_a, gpio.tempo_b, gpio.tempo_switch, config.cfg.get("rotary_tempo_mult", 1) )
    
    from history import HistoryManager
    history = HistoryManager(config.HISTORY_JSON)

    from battery import Battery
    battery = Battery(
        config.BATTERY_JSON,
        config.BATTERY_CALIBRATION_JSON,
    )
    
    from microphone import Microphone
    microphone = Microphone( gpio.microphone_pin, config.cfg["mic_test_mode"] )
    
    from organtuner import OrganTuner
    organtuner = OrganTuner()

    from tunemanager import TuneManager
    tunemanager = TuneManager(config.TUNELIB_FOLDER, config.TUNELIB_JSON, config.LYRICS_JSON, config.SYNC_TUNELIB )
    
    from player import MIDIPlayer
    player = MIDIPlayer()

    from setlist import Setlist
    setlist = Setlist()

    from poweroff import PowerManager
    poweroff = PowerManager()

    import webserver
    run_webserver = webserver.run_webserver



 





