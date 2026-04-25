# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
# WiFi connection manager. Connects to station mode SSIDs and
# publishes the AP mode SSID
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
from time import ticks_ms, ticks_diff

from drehorgel import config, timezone, led
from minilog import getLogger
import scheduler
import blemcs

# 15 seconds waiting for this device in station mode to connect to an AP
# After this time, the device will try with the other AP
_STATION_WAIT_FOR_CONNECT = 15_000

# WiFi error status codes. This allows to show the error
# name for WiFi errors (such as "STAT_WRONG_PASSWORD") instead
# of error codes (such as 202).
STATUS_CODE_DICT = { getattr(network, errcode): errcode for errcode in dir(network) if errcode.startswith("STAT_")}



class WiFiManager:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.sta_if_status = ""
        # Connect in background to both interfaces
        self.ap_if = network.WLAN(network.AP_IF)
        self.sta_if = network.WLAN(network.STA_IF)
        network.hostname(config.name)

        self.sta_if_ssid = ""

        # If there was a soft reset, get rid of previous connect
        # disconnect() before active(False) may raise Wifi error
        self.sta_if.active(False)
        self.ap_if.active(False)

        # Configure hostname before setting .active(True)
        # Works for both AP and STA_IF mode
        network.hostname(config.name)
        self.sta_if_cancel_event = asyncio.Event()

        # Pass info to Bluetooth advertiser.
        if config.advertise_bt:
            self.blemcs = blemcs.BLEMCS( config.name )
        else:
            self.blemcs = blemcs.BLEnull()
        self.blemcs.set_characteristic( "stassid1", config.access_point1 )
        self.blemcs.set_characteristic( "stassid2", config.access_point2 )
        self.blemcs.set_characteristic( "apssid", config.name )
        self.blemcs.set_characteristic( "staip1", "" )
        self.blemcs.set_characteristic( "staip2", "" )
        self.blemcs.set_characteristic( "apip", config.ap_ip )

        self.blemcs.start_advertising()

    async def async_init(self):
        # Start background task to connect STA_IF and AP_IF
        self.start_task = asyncio.create_task(self._start_interfaces())
        # Yield to give time for start_task to start
        await asyncio.sleep_ms(100)
        self.logger.debug("init ok")

    async def _start_interfaces(self):
        try:
            self.start_station_task = asyncio.create_task(
                self._start_station_interface()
            )
            await asyncio.sleep_ms(100)
            # In parallel start the access point interface
            await self._start_ap_interface()
        except Exception as e:
            self.logger.exc(e, "in _start_interfaces")

    async def _start_ap_interface(self):
        try:
            self.ap_if.active(True)
            self.ap_if.config(
                ssid=config.name,
                key=config.get_password("ap_password"),
                security=4,
            )
            apip = config.ap_ip
            self.ap_if.ifconfig((apip, "255.255.255.0", apip, apip))
            self.logger.debug(
                f"AP mode started ssid {config.name} IP {self.ap_if.ipconfig('addr4')}"
            )
            self.blemcs.set_status( "ap", "a" )
        except Exception as e:
            self.logger.exc(e, "in _start_ap_interface")

        # The timeout is some minutes for a client to connect to the AP WiFi
        # Once connected, there is no limit on time to use the AP WiFi connection
        await asyncio.sleep(config.ap_max_idle)
        if not self.ap_if.isconnected():
            self.ap_if.active(False)
            self.logger.debug("AP mode idle, disconnected")
            self.blemcs.set_status( "ap", "i" )
            # This will probably also disconnect sta_if
            # if not in use.
            # Reinit the station interface just in case
            self.sta_if.active(True)
        else:
            # Now connected as AP, cancel station interface to save energy
            self.sta_if_cancel_event.set()
            self.logger.debug("AP mode in use, station mode cancelled")

    async def _start_station_interface(self):
        try:
            while True:
                # Try with each AP defined, reconnect if it gets disconnected.
                for ap in ("1", "2"):
                    await asyncio.sleep_ms(500) # avoid tight loop
                    # Will fail if not configured, but AP should start anyhow.
                    ssid = getattr( config, "access_point" + ap )
                    if not ssid:
                        continue
                    self.sta_if_ssid = ssid
                    password = config.get_password("password" + ap)
                    self.logger.debug(
                        f"_start_station_interface for ssid={self.sta_if_ssid=}"
                    )
                    self.blemcs.set_status( "sta"+ap, "b" )
                    await self._station_connect_to_ap(
                        self.sta_if_ssid, password
                    )
                    if self.sta_if.isconnected():
                        led.connected()
                        await self.loginfo(
                            f"Connected to {self.sta_if.config('ssid')} IP {self.sta_if.ipconfig('addr4')} hostname {network.hostname()}"
                        )
                        timezone.network_up()
                        self.blemcs.set_status( "sta"+ap, "c" )
                        self.blemcs.set_characteristic( "staip"+ap, self.sta_if.ipconfig('addr4')[0] )
                        
                    # isconnected does not need to RequestSlice
                    while self.sta_if.isconnected():
                        # Test every 10 seconds if still connected
                        await asyncio.sleep(10)
                    self.blemcs.set_status( "sta"+ap, "n" )
                    self.blemcs.set_characteristic( "staip"+ap, "" )
                    # Reset sta_if before trying again
                    # self.sta_if.disconnect()
                    self.sta_if.active(False)
                    await asyncio.sleep(1)
                if self.sta_if_cancel_event.is_set():

                    # If cancelled, then
                    # don't restart anymore
                    await self.loginfo(
                        "Station interface cancelled by AP interface"
                    )
                    return
                # else try to connect again to next AP in config.json

        except Exception as e:
            self.logger.exc(e, "in _start_station_interface")

    async def _station_connect_to_ap(self, access_point, password ):
        # Connect station interface to a router or wifi hotspot

        try:

            self.sta_if.active(True)
            # Power modes for WiFi
            # Hard reset default is network.WLAN.PM_PERFORMANCE=1
            # No clear difference beteen PM_NONE and PM_PERFORMANCE...
            # self.sta_if.config(pm=network.WLAN.PM_NONE)
            try:
                self.sta_if.connect(access_point, password)

                start_time = ticks_ms()
                while (not self.sta_if.isconnected() and 
                       ticks_diff(ticks_ms(), start_time) < _STATION_WAIT_FOR_CONNECT):
                    await asyncio.sleep_ms(100)

            except Exception as e:
                # OSError: Wifi Internal Error (recoverable) happens
                # if connecting on a sta_if without disconnectig.
                self.logger.exc(
                    e,
                    f"Station interface: Error during connection {access_point=}",
                )
                self.sta_if_status = access_point + str(e)
                return

            if self.sta_if.isconnected():
                self.sta_if_status = access_point + " connected"
                return
            # Problems? Get the status and log it
            status = self.sta_if.status()
            self.sta_if_status = access_point + " " + str(status) + " " + STATUS_CODE_DICT.get( status, "" )
            await self.loginfo(
                f"Status for {self.sta_if_status}, could not connect to {access_point}"
            )
        except Exception as e:
            self.logger.exc(e, "in _station_connect_to_ap")
            self.sta_if_status = access_point + " " + str(e)
            
    def get_status(self):
        # Detailed wifi status for diag.html
        return {
            "sta_if_status": self.sta_if_status,
            "sta_if_ssid": self.sta_if_ssid,
            "sta_if_connected": self.sta_if.isconnected(),
            "sta_if_ip": self.sta_if.ipconfig("addr4"),
            "sta_if_active": self.sta_if.active(),
            "ap_if_connected": self.ap_if.isconnected(),
            "ap_if_ip": self.ap_if.ipconfig("addr4"),
            "ap_if_ssid": config.name,
            "ap_if_active": self.ap_if.active(),
            "hostname": network.hostname(),
            "description": config.description,
        }

    def sta_isconnected(self):
        # See mcserver
        return self.sta_if.isconnected()

    def sta_if_scan(self):
        return self.sta_if.scan()

    async def loginfo(self, message):
        try:
            async with scheduler.RequestSlice( "wifimanager log.info", 100, 10_000):  
                # logging can take about 100 msec
                self.logger.info(message)
        except Exception:
            # Don't log info messages if playing
            # does not allow it
            pass

