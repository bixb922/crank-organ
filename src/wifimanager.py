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
#       Fallback if station mode does not work. 
import asyncio
import network

from drehorgel import config, timezone, led
from minilog import getLogger
import blemcs

# 15 seconds waiting for this device in station mode to connect to an AP
# After this time, the device will try with the other AP
# Normally it takes 4 or 5 seconds to connect
_STATION_WAIT_FOR_CONNECT = const(15)
# Time to sleep between WiFi status checks
_SLEEP_INTERVAL = const(10) 
# Time to sleep after both station SSIDs fail until attempting to
# connect again. This leaves time to connect on the station AP.
# If this time is too long, a reboot will speed up things anyhow
_STATION_WAIT_FOR_RETRY = const(60)




class WiFiManager:
    def __init__(self):
        self.logger = getLogger(__name__)
        self.sta_if_status = ""
        # Connect in background to both interfaces
        self.ap_if = network.WLAN(network.AP_IF)
        self.sta_if = network.WLAN(network.STA_IF)

        self.sta_if_ssid = ""

        # If there was a soft reset, get rid of previous connect
        # and of info stored inside the ESP32S3 about WiFi connections.
        # disconnect() before active(False) may raise Wifi error
        self.sta_if.active(False)
        self.ap_if.active(False)

        # Configure hostname before setting .active(True)
        # Works for both AP and STA_IF mode
        network.hostname(config.name)

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
        # Rest of __init__ is in self.async_init().

    async def async_init(self):

        # Start background task to connect STA_IF and AP_IF
        self.station_task = asyncio.create_task(self._station_process())
        self.ap_task = asyncio.create_task(self._ap_process())
        # Yield to give time for task to start
        # (could also loop while self.sta_if_ssid == ""
        await asyncio.sleep_ms(100)

    def _start_ap_interface(self):

        # Don't start AP mode again if already active.
        if self.ap_if.active():
            return
       
        self.ap_if.active(True)
        # It is not possible to set ap_if.config(pm=PM_xxx) 
        # for AP mode: OSError: Wifi Invalid Mode

        self.ap_if.config(
            ssid=config.name,
            key=config.get_password("ap_password"),
            security=4,
        )
        apip = config.ap_ip
        self.ap_if.ifconfig((apip, "255.255.255.0", apip, apip))
        self.logger.debug(
            f"AP mode started ssid={config.name} IP={self.ap_if.ipconfig('addr4')}"
        )
        self.blemcs.set_status( "ap", "a" )

    async def _ap_process(self):
        # for report only
        while True:
            while not self.ap_if.isconnected():
                await asyncio.sleep(_SLEEP_INTERVAL)
            await self.logger.async_info("AP mode connected")
            while self.ap_if.isconnected():
                await asyncio.sleep(_SLEEP_INTERVAL)
            await self.logger.async_info("AP mode disconnected")

    async def _station_process(self):
        while True:
            # Try with each AP defined, reconnect if it gets disconnected.
            for n in ("1", "2"):
                try:
                    await self._station_session(n)
                except Exception as e:
                    self.logger.exc(e, "in _station_process")
                    self.sta_if_status = "Exception "+str(e)
                self.sta_if.active(False)
                await asyncio.sleep(1)

            # None of the 2 STA SSIDs could be connected. Or STA SSID
            # was connected and then connected.
            # Or AP mode has active client.
            # It is time to activate AP mode for fallback (i.e. forever)
            self._start_ap_interface()

            # Retry STA SSID some nice time later
            # Enough time to try a AP mode connect
            await asyncio.sleep(_STATION_WAIT_FOR_RETRY)


    async def _station_session(self, n):
        ssid = getattr( config, "access_point" + n )
        if self._ap_has_traffic() or not config.wifi_configured(int(n)) or not ssid:
            # If AP mode has a traffic, don't search for a STA SSID
            # AP mode is fallback, don't disturb AP mode searching for a SSID!
            # If user wants to search for SSID, reboot is needed. Or stop
            # using AP mode.
            # Also: just skip if not configured
            return
        self.sta_if_ssid = ssid
        self.logger.debug( f"WiFi starting connection to ssid={self.sta_if_ssid=}")
        self.blemcs.set_status( "sta"+n, "b" )
        if await self._station_connect(
            ssid, config.get_password("password" + n)
            ):
            led.connected()
            await self.logger.async_info( f"Connected to {self.sta_if.config('ssid')} IP {self.sta_if.ipconfig('addr4')} hostname {network.hostname()}")
            timezone.network_up()
            self.blemcs.set_status( "sta"+n, "c" )
            self.blemcs.set_characteristic( "staip"+n, self.sta_if.ipconfig('addr4')[0] )
            # Also start AP for fun, not because fallback is sorely needed.
            if not config.ap_fallback_only:
                self._start_ap_interface()

        # Loop until connection stops
        while self.sta_if.isconnected():
            await asyncio.sleep(_SLEEP_INTERVAL)
        
        # Lost connection, try again la
        self.blemcs.set_status( "sta"+n, "n" )
        self.blemcs.set_characteristic( "staip"+n, "" )
        
    async def _station_connect(self, ssid, password ):
        # Connect station interface to a router or wifi hotspot
        self.sta_if.active(True)
        # Power modes for WiFi
        # Hard reset default is network.WLAN.PM_PERFORMANCE=1
        # No clear difference beteen PM_NONE and PM_PERFORMANCE...
        # self.sta_if.config(pm=network.WLAN.PM_NONE)

        # Now connect to the SSID
        self.sta_if.connect(ssid, password)

        for _ in range(_STATION_WAIT_FOR_CONNECT):
            if self.sta_if.isconnected():
                self.sta_if_status = ssid + " connected"
                return True
            if self._ap_has_traffic():
                self.sta_if_status = "AP mode active"
                await self.logger.async_info(
                                f"Stopped connecting to {ssid}, {self.sta_if_status}"
                            )
                return False
            await asyncio.sleep(1)

        
        # Problems? Get the status and log it
        status = self.sta_if.status()
        self.sta_if_status = ssid + " " + str(status) + " " + self.translate_status( status )
        await self.logger.async_info(
            f"Status for {self.sta_if_status}, could not connect to {ssid}"
        )
            
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

    def translate_status(self, status):
        # WiFi error status codes. This allows to show the error
        # name for WiFi errors (such as "STAT_WRONG_PASSWORD") instead
        # of error codes (such as 202).
        status_code_dict = { getattr(network, errcode): errcode for errcode in dir(network) if errcode.startswith("STAT_")}
        return status_code_dict.get( status, "" )
    
    def sta_isconnected(self):
        # See mcserver
        return self.sta_if.isconnected()

    def sta_if_scan(self):
        try:
            return self.sta_if.scan()
        except OSError:
            # Probably only AP mode is active, no WiFi scan.
            return []
    
    def _ap_has_traffic(self):
        if self.ap_if.isconnected():
            from webserver import is_active
            # Calculate prefix, i.e. if config.ap_ip is "192.168.144.1"
            # then the prefix for all assigned addresses
            # on that subnet is "192.168.144"
            # Since /get_progress URL is checked every 2 to 5 seconds
            # asking for 20 seconds of inactivity is on the safe side.
            return is_active(20_000, ".".join(config.ap_ip.split(".")[0:3]))
        # if ap_if is not connected, it cannot have traffic...