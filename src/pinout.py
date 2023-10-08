# (c) 2023 Hermann Paul von Borries
# MIT License
# ESP32-S3 GPIO pin definitions and port expander MCP23017 pin definitios

import asyncio
import json
import os
import machine
import sys
import time
from mcp23017 import MCP23017
from random import randint
import config
import midi


pinout_files = []

description = None
neopixel_pin = None
tachometer_pin = None
microphone_pin = None
touchpad_pin = None
all_valid_midis = None

_no_action = lambda *x: None

def define_description( x ):
    global description
    description = x
def define_neopixel( x ):
    global neopixel_pin
    neopixel_pin = int(x)
def define_tachometer( x ):
    global tachometer_pin
    tachometer_pin = x
def define_microphone( x ):
    global microphone_pin
    microphone_pin = x
def define_touchpad( x ):
    global touchpad_pin
    touchpad_pin = x
def append_valid_midis( instrument, midi_num ):
    if midi_num :
        n = midi.Note( instrument, midi_num )
        if n:
            all_valid_midis.append( midi.Note( instrument, midi_num ) )

pinout_actions = {
    "description": lambda x: define_description(x),
    "neopixel": lambda x : define_neopixel(x),
    "tachometer": lambda x : define_tachometer(x),
    "microphone": lambda x : define_microphone(x),
    "touchpad": lambda x : define_touchpad(x),
    "gpio.midi": lambda pin, instrument, midi_num, rank: append_valid_midis( instrument, midi_num ), 
    "mcp.midi": lambda pin, instrument,  midi_num, rank: append_valid_midis( instrument, midi_num )
    
}

def get_pinout_filename():
    try:
        with open( config.PINOUT_FILE) as file:
            filename = file.read()
    except:
         filename = pinout_files[0]
    return filename

def read_current_pinout_json():
    filename = get_pinout_filename()
    return read_pinout_json( filename )

def read_pinout_json( filename ):
    with open( config.DATA_FOLDER + "/" + filename ) as file:
        return json.load( file )
    

def load_pin_info( ):
    global tachometer_pin, microphone_pin, neopixel_pin
    global description, all_valid_midis, pinout_files
    # Pinout files have to be in the data folder,
    # have type json and have "_note_" in the file name.
    # and start with a digit 1 to 9. 
    # Examples: 20_note_Carl_Freil.json, 31_note_Raffin.json)
    pinout_files = []
    for fn in os.listdir(config.DATA_FOLDER):
        # Pinout files must have the form <nnn>_note_<name>.json
        # where <nnn> is the number of notes of the scale and
        # <name> is the name itself, example 20_note_Carl_Frei.json
        # where 20 is the number of notes and Carl_Frei is the name.
        if (fn.endswith("json") and 
            "_note_" in fn and
            "1" <= fn[0:1] <= "9"):
            pinout_files.append( fn )
	if len( pinout_files ) == 0:
		print("Error: no pinout files found in /data")
    neopixel_pin = ""
    tachometer_pin = ""
    microphone_pin = ""
    touchpad_pin = ""
    all_valid_midis = []
    description = ""
    
    # Parse pinout to get general definitions
    pinout_json = read_current_pinout_json()

    do_actions( pinout_json, pinout_actions )
    
    # Sort valid midis
    all_valid_midis.sort( key=lambda m: m.hash )
        

def define_solenoids( solenoid_def ):
    # Called by solenoid._init()
    solenoid_actions = {

        "gpio.midi": lambda pin, instrument, midi_num, rank: solenoid_def.define_gpio_midi( pin, midi.Note( instrument, midi_num ), rank ),
        "i2c": solenoid_def.define_i2c, # sda, scl
        "mcp23017": solenoid_def.define_mcp23017, # address
        "mcp.midi": lambda pin, instrument, midi_num, rank: solenoid_def.define_mcp_midi( pin, midi.Note( instrument, midi_num ), rank )
    }
    
    pinout_json = read_current_pinout_json()
    do_actions( pinout_json, solenoid_actions )
    
def do_actions( pinout_json, actionlist ):
    for pd in pinout_json:
        if pd[0] in actionlist:
            actionlist[pd[0]]( *pd[1:]) 

def get_description( filename ):
    pinout_json = read_pinout_json( filename )
    for pd in pinout_json:
        if pd[0] == "description":
            return pd[1]
        
def pinout_list():
    pl = []
    for filename in pinout_files:
        pl.append( (  get_description( filename ), filename ) )
    return pl

def set_pinout_filename( newfilename ):
    if newfilename not in pinout_files:
        raise ValueError( f"Invalid pinout file {newfilename}" )
    with open( config.PINOUT_FILE, "w") as file:
        file.write( newfilename )
    load_pin_info()
    import organtuner
    organtuner.pinout_changed()
    
def save( newjson ):
    if( len(newjson)<10):
        raise ValueError("new pinout json too short")
    # Convert all numbers to int before storing
    for pd in newjson:
        for i, item in enumerate(pd):
            try:
                pd[i] = int(pd[i])
            except:
                pass
    # Replace current pinout filename
    filename = config.DATA_FOLDER + "/" + get_pinout_filename()
    with open( filename, "w") as file:
        json.dump( newjson, file )
    
    import organtuner
    organtuner.pinout_changed()
        
def get_all_valid_midis():
    return all_valid_midis

# ========================
# Test functions
# ========================
def basicTestGPIO( gpio_pin ):
    # Test a GPIO pin. Sometimes this does not work,
    # is random because of ambient electromagnetic noise.
    gp = machine.Pin( gpio_pin, machine.Pin.IN, machine.Pin.PULL_UP )
    with_pull_up = gp.value()
    gp = machine.Pin( gpio_pin, machine.Pin.IN, machine.Pin.PULL_DOWN )
    with_pull_down = gp.value()
    gp = machine.Pin( gpio_pin, machine.Pin.IN )
    no_pull = gp.value()
    
    n = with_pull_up*2 + with_pull_down
    # 00 = something pulls down for all cases. Might be a ULN2803 or
    # some other device.
    # 01 = ??? probably not connected
    # 10 = input follows the pull ups, not connected
    # 11 = there is something that pulls up this pin, example: I2C
    return ("DEV", "???", "NC", "I2C")[n]

# Test several times if something pulls the voltage
# up or down on the pin
def testGPIO( pin, repeat=10 ):
    res = set()
    for _ in range(repeat):
        time.sleep_ms(1)
        r = basicTestGPIO( pin )
        res.add( r )
    if len( res ) == 1:
        return res.pop()
    else:
        return "FLO"

# Used by solenoid.py to check if something on I2C
def testI2Cconnected( sda, scl ):   
    sdaok = testGPIO( sda ) == "I2C"
    sclok = testGPIO( scl ) == "I2C"
    return ( sdaok, sclok )

# Used by web page to test one pin - physical chip level
async def web_test_gpio( gpio_pin ):
    gpio=machine.Pin( gpio_pin, machine.Pin.OUT )
    for _ in range(8):
        gpio.value(1)
        await asyncio.sleep_ms( 500 )
        gpio.value(0)
        await asyncio.sleep_ms( 500 )
        
# Used by web page to test one pin of MCP23017 physical chip level       
async def web_test_mcp( sda, scl, mcpaddr, mcp_pin ):
    i2c = machine.SoftI2C(
        scl=machine.Pin(scl), 
        sda=machine.Pin(sda) )
    mcp = MCP23017( i2c, mcpaddr )
    mcp[mcp_pin].output()
    for _ in range(8): 
        mcp[mcp_pin].output(1)
        await asyncio.sleep_ms( 500 )
        mcp[mcp_pin].output(0)
        await asyncio.sleep_ms( 500 )
    
def get_random_midi_note():
    return all_valid_midis[ randint( len(all_valid_midis) ) ]

load_pin_info()

