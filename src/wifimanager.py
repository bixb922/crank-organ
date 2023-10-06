# WiFi connection manager. Connects to station mode SSIDs and
# publishes the AP mode SSID
# >>> Problem? DISCONNECTS FROM AP_IF WHEN ACTIVATING STA_IF
#
# 2 modes:
#   STA_IF mode
#       with home router
#       with cell phone router
#       If home router is not accessible, then it will cycle through both
#  AP_IF mode
#       Fallback if station mode does not work. Is active for 2 minutes
#       only after power on, then it will turn off if inactive.

import asyncio
import network
import ntptime
import time
import gc

import config
from minilog import getLogger
import scheduler

# 15 seconds waiting for this device in station mode to connect to an AP
# After this time, the device will try with the other AP
_STATION_WAIT_FOR_CONNECT = 15_000

async def async_init():
    global _logger, _sta_if, _ap_if, _start_task, _sta_if_status, _sta_if_ap, _sta_if_cancel_event
    _logger = getLogger( __name__ )
    _logger.debug("_init start")
    _sta_if_status = ""
    # Connect in background to both interfaces
    _ap_if = network.WLAN( network.AP_IF )
    _sta_if = network.WLAN( network.STA_IF )

    _sta_if_ap = ""
    
    # If there was a soft reset, get rid of previous connect
    # disconnect() before active(False) may raise Wifi error
    _sta_if.active( False )
    _ap_if.active( False )
    
    # Configure hostname before setting .active(True)
    # Works for both AP and STA_IF mode
    network.hostname( config.cfg["name"] )
    _logger.debug(f"WiFi hostname {network.hostname()}")
    # Start background task to connect STA_IF and AP_IF 
    _start_task = asyncio.create_task( _start_interfaces() )
    _sta_if_cancel_event = asyncio.Event()
    # Yield to give time for sta_if to start
    await asyncio.sleep_ms(100)
    _logger.debug("init ok")
    
async def _start_interfaces():
    global _start_station_task
    try:
        _start_station_task = asyncio.create_task( _start_station_interface() )
        # In parallel start the access point interface
        await _start_ap_interface()
    except Exception as e:
        _logger.exc(e, "in _start_interfaces" )
        
async def _start_ap_interface():
    try:
        _ap_if.active(True)
        _ap_if.config(ssid = config.cfg["name"], 
                     key = config.get_password("ap_password"), 
                     security = 4)
        apip = config.cfg.get( "ap_ip", "192.168.144.1" )
        _ap_if.ifconfig((apip, '255.255.255.0', apip, apip))
        _logger.debug(f"AP mode started ssid {config.cfg['name']} config {_ap_if.ifconfig()}")

    except Exception as e:
        _logger.exc(e, "in _start_ap_interface" )
    
    await asyncio.sleep( config.get_int("ap_max_idle", 120 )  ) 
    if not _ap_if.isconnected():
        _ap_if.active( False )
        # This will probably also disconnect sta_if?
        _logger.debug("AP mode idle, disconnected")
    else:
        # Now connected as AP, cancel station interface to save energy
        _sta_if_cancel_event.set()
        _sta_if.active(False)
        _logger.debug("AP mode in use, station mode cancelled")
    
async def _start_station_interface():
    global _sta_if_ap
    try:
        while True:
            # Try with each AP defined, reconnect if it gets disconnected.
            for ap in ("1","2"):
                # Will fail if not configured, but AP should start anyhow.
                _sta_if_ap = config.cfg["access_point" + ap]
                password = config.get_password( "password" + ap )
                _logger.debug(f"_start_station_interface for {_sta_if_ap=}" )
                await _station_connect_to_ap( _sta_if_ap, password )
                if _sta_if.isconnected():
                    async with scheduler.RequestSlice("WifiManager log", 150, 3000 ):
                        _logger.info(f"Connected to {_sta_if.config('ssid')} network config {_sta_if.ifconfig()} hostname {network.hostname()}")
                    
                    # Get time (if not set already)
                    await _get_ntp_time()
                    
                # isconnected does not need to RequestSlice
                while _sta_if.isconnected():
                    # Test every 10 seconds if still connected
                    await asyncio.sleep(10)

                # Reset sta_if before trying again
                # _sta_if.disconnect()
                _sta_if.active( False )
                await asyncio.sleep(1)
            if _sta_if_cancel_event.is_set():
                # If cancelled, then disactivate sta_if
                _sta_if.active( False )
                # Don't restart anymore
                _logger.info("Station interface cancelled by AP interface")
                return
            # else try to connect again to next AP in config.json
            
    except Exception as e:
        _logger.exc(e, "in _start_station_interface")
        
        
        
async def _station_connect_to_ap( access_point, password ):
    # Connect station interface to a router or wifi hotspot
    global _sta_if_status
   
    try:
        _sta_if.active( True )
        try:
            _sta_if.connect( access_point, password )
            start_time = time.ticks_ms()
            while not _sta_if.isconnected():
                await asyncio.sleep_ms( 100 )
                if time.ticks_diff( time.ticks_ms(), start_time ) > _STATION_WAIT_FOR_CONNECT:
                    break
                    
        except Exception as e:
            # OSError: Wifi Internal Error (recoverable) happens
            # if connecting on a sta_if without disconnectig.
            _logger.exc( e, f"Station interface: Error during connection {access_point=}")
            _sta_if_status = access_point + str(e)
            return
        
        if _sta_if.isconnected():
            _sta_if_status = access_point + " connected"
            return
        
        # Problems? Get the status and log it
        status = _sta_if.status()
        _sta_if_status = access_point + " " + str(status)
        _logger.info(f"Status'({_sta_if_status})', could not connect to {access_point}")
    except Exception as e:
        _logger.exc(e, "in _station_connect_to_ap")
        _sta_if_status = access_point + " " + str(e)
        
async def _get_ntp_time():
    if time.localtime()[0] >= 2023:
        # Time already set
        return
    # Retry only few times. Clock time is only relevant for the
    # event log file time stamps, no critical use.
    for _ in range(2):
        try:
            async with scheduler.RequestSlice("WiFiManager ntp time", 200, 3000 ):
                ntptime.settime()
            return
        except Exception as e:
            _logger.exc( e, "exception in ntptime" )
            # OSError -202 means server not found, happens once in a while.
            # Will run with UTC time.
        await asyncio.sleep_ms(1000)
    
def get_status():
    # Detailed wifi status for diag.html
    return { "sta_if_status": _sta_if_status,
             "sta_if_ap": _sta_if_ap,
             "sta_if_connected": _sta_if.isconnected(),
             "sta_if_ip": _sta_if.ifconfig()[0],
             "sta_if_active": _sta_if.active(),
             "ap_if_connected": _ap_if.isconnected(),
             "ap_if_ip": _ap_if.ifconfig()[0],
             "ap_if_ssid": config.cfg["name"],
             "ap_if_active": _ap_if.active(),
             "hostname": network.hostname() ,
             "description": config.cfg["description"]
             }

def sta_if_scan():
    return _sta_if.scan()

asyncio.run( async_init() )              
            
