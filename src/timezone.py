# (c) 2023 Hermann Paul von Borries
# MIT License
import time
import ntptime
import asyncio
import machine

import scheduler
import fileops

# Don't use config.py, because timezone is needed before
TZFILE = "data/timezone.json"
NTP_RETRIES = 3

# Time zone longName if no time zone info is available
NO_TZ_INFO = "no tz info"

class TimeZone:
    def __init__(self):
        self.ntp_task = None
        self.logger = None
        # No logger yet, because of import circularity

        self.tzinfo = fileops.read_json( TZFILE, {
            "offset": 0,
            "shortName": "UTC",
            "longName": NO_TZ_INFO,
            "timestamp": 0
        } )


    def setLogger(self, getLogger):
        self.logger = getLogger(__name__)
       

    def network_up(self):
        # wifimanager calls here when network is up
        if self.ntp_task:
            # Avoid reentering task while it is active
            return
        self.ntp_task = asyncio.create_task(self._ntp_process())

    async def _ntp_process(self):
        # Get ntp time, then update time zone 
        # But do nothing if time has already been set 
        # maybe by browser, maybe previous to a soft reset
        if self.has_time():
            return # Clock already set
        # Try several times to get time from ntp server
        await self._get_ntp_time()
        # Set RTC with this time + time zone offset
        self.set_rtc( time.time() )
    
    def has_time( self ):
        # is time after 2024/1/1?
        # i.e. has time already been set by ntp, browser
        # or previous to soft reset?
        return time.time() > 756864000
    
    def set_rtc( self, timestamp ):
        # Prepare a time tuple as argument for RTC
        t = time.localtime(timestamp - self.tzinfo["offset"] )
        # Set this as the local time, to be returned
        # by time.localtime() and time.time()
        # year, month, day, weekday, hour, minute, second, subsecond
        machine.RTC().datetime( (t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))

    async def _get_ntp_time(self):
        # Retry a few times.
        retry_time = 3000 # Gets duplicated for every retry
        for _ in range(NTP_RETRIES):
            try:
                async with scheduler.RequestSlice("ntptime", 1000):
                    # ntptime.settime is not async, will block
                    ntptime.settime()
                return 
            except (asyncio.TimeoutError, OSError) as e:
                self.logger.info(f"Recoverable ntptime exception {repr(e)}") # type:ignore
                # RequestSlice did not give slice, retry later
                # OSError -202 means server not found, happens once in a while
                pass
            except Exception as e:
                self.logger.info(f"Unrecoverable ntptime exception {repr(e)}") # type:ignore
                return

            await asyncio.sleep_ms(retry_time)
            # ntp servers don't like frequent retries...
            # Duplicate retry time for each time
            retry_time *= 2

    def set_time_zone( self, newtz:dict ):
        # Called from webserver with /set_time_zone
        # Which in turn is called from common.js for each hard page load
        newtimestamp = newtz["timestamp"]
        del newtz["timestamp"]
        if newtz != self.tzinfo:
            # Don't replace self.tzinfo, better to show times with
            # old timezones instead of mixing new time zone with old offet.
            fileops.write_json( newtz, TZFILE, keep_backup=True )
            self.logger.info("Timezone info updated, takes effect next reboot") # type:ignore
        
        # If we don't have ntptime, use the timestamp provided
        # by the browser. This is normally case if using AP mode
        # but sometimes ntptime fails, since there is no guarantee
        # of service for ntptime. And also: if setting a new
        # time zone, this sets the time and resets the RTC
        # to the new time zone.
        # Convert from Unix epoch to ESP32 epoch and
        # set RTC. 
        if self.has_time():
            return # NTP or browser has already set time.
        self.set_rtc( newtimestamp - 946_684_800)
        self.logger.info("Time set by browser") # type:ignore
        
    def get_time_zone_info( self ):
        return self.tzinfo
    
    def now_timestamp(self):
        # time.time() is already in local time, no need to add offset
        return time.time() 
    
    def now(self):
        t = time.localtime(self.now_timestamp())
        if self.has_time():
            return t
        # Don't apply time zone if no clock set (no ntptime yet)
        return time.localtime()

    def now_ymdhms(self):
        t = self.now()
        return (
            f"{t[0]:02d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
        )

    def now_ymdhm(self):
        return self.now_ymdhms()[0:-3]

    def now_hms(self):
        # yyyy-mm-dd hh:mm:ss
        # 0123456789012345
        return self.now_ymdhms()[11:]

    def now_ymd(self):
        return self.now_ymdhms()[0:10]

    def now_ymdhmsz(self):
        if self.has_time(): 
            return self.now_ymdhms() + self.tzinfo["shortName"]
        # No ntptime (yet)
        return self.now_hms()

