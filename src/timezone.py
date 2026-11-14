# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
from time import time, localtime
import ntptime
import asyncio
import machine

import scheduler
import fileops

# To test starting RTC from 0: 
# from network import WLAN,STA_IF,AP_IF;WLAN(STA_IF).active(False);WLAN(AP_IF).active(False);import machine;machine.RTC().init((2000,1,1,0,0,0,0,0));machine.soft_reset();

# Don't use config.py, because timezone is needed before
_TZFILE = const("data/timezone.json")
_NTP_RETRIES = const(3)

# Time zone longName if no time zone info is available
_NO_TZ_INFO = const("no tz info")

# Difference to convert from Unix epoch (1970/1/1) to ESP32 epoch (2000/1/1)
# 30 years in seconds
_ESP32_EPOCH = const(946_684_800)

class TimeZone:
    def __init__(self):
        self.ntp_task = None

        # No logger yet, because of import circularity

        self.tzinfo = fileops.read_json( _TZFILE, {
            "offset": 0,
            "shortName": "UTC",
            "longName": _NO_TZ_INFO,
            "timestamp": 0
        } )


    def set_logger(self, getLogger):
        self.logger = getLogger(__name__)
       

    def network_up(self):
        # wifimanager calls here when network is up
        if self.ntp_task:
            # Avoid reentering task while it is active
            return
        self.ntp_task = asyncio.create_task(self._ntp_process())

    async def _ntp_process(self):
        # Wait for things to settle a bit, this isn't so high priority.
        # And maybe the browser already did the work.
        await asyncio.sleep_ms(2000)

        # Retry a few times.
        retry_time = 3000 # Gets duplicated for every retry
        for _ in range(_NTP_RETRIES):
            if self.has_time():
                return # browser already sent the time (/set_time_zone)
            try:
                async with scheduler.RequestSlice("ntptime", 2000):
                    # ntptime.settime is not async, will block
                    ntptime.settime()
                self.logger.async_info("Time set by NTP")
                return
            except (asyncio.TimeoutError, OSError) as e:
                self.logger.async_info(f"Recoverable ntptime exception {repr(e)}") 
                # RequestSlice did not yield slice, retry later
                # OSError -202 means server not found, happens once in a while
                pass
            except Exception as e:
                self.logger.async_info(f"Unrecoverable ntptime exception {repr(e)}") 
                return

            await asyncio.sleep_ms(retry_time)
            # ntp servers don't like frequent retries so
            # duplicate retry time for each retry.
            retry_time *= 2
        # Out of retries. Browser will eventually set time.

    def has_time( self ):
        # Has time been set by ntp or browser?
        return self.is_valid( time() )
    
    def is_valid( self, timestamp ):
        # 316_000_000 some time in 2010.
        # 2_380_968_000 = some time  in  2075.
        return 316_000_000 <= timestamp <= 2_380_968_000
    
    def _set_rtc( self, timestamp ):
        # Prepare a time tuple as argument for RTC
        t = localtime(timestamp)
        # year, month, day, weekday, hour, minute, second, subsecond
        machine.RTC().datetime( (t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))

    async def set_time_zone( self, newtz:dict ):
        # Called from webserver with /set_time_zone
        # which in turn is called from common.js every now and then.
        newtimestamp = newtz["timestamp"]
        del newtz["timestamp"] # doesn't need to get saved to flash.
        if newtz != self.tzinfo:
            # Don't replace self.tzinfo, better to show times with
            # old timezones instead of mixing new time zone with old offset
            # until reboot.
            fileops.write_json( newtz, _TZFILE, keep_backup=True )
            self.logger.async_info("Timezone info updated, takes effect next reset") 
        
        # If we don't have ntptime, use the timestamp provided
        # by the browser. This is normally case if using AP mode
        # but sometimes ntptime fails, since there is no guarantee
        # of service for ntptime. And also: if setting a new
        # time zone, this sets the time
        if self.has_time():
            return # NTP or browser has already set time.
        # Check that time is in a reasonable range
        if self.is_valid( newtimestamp ):
            self._set_rtc( self.unix_to_esp32(newtimestamp) )
            self.logger.async_info("Time set by browser") 
        else:
            self.logger.async_info("Ignoring time set by browser, out of range")
        
    def get_time_zone_info( self ):
        return self.tzinfo


    def now_ymdhms(self):
        return self.ymdhms( time() )

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

    # Same but with timestamp instead of now. Not all variants are needed
    #def ymd(self, timestamp):
        # "2026-09-18"
        #  1234567890
    #    return self.ymdhms(timestamp)[0:10]

    #def ymdhm(self, timestamp):
    #    return self.ymdhms(timestamp)[0:-3]
    
    def ymdhms(self, timestamp):
        if self.has_time():
            timestamp -= self.tzinfo["offset"]
        try:
            t = localtime(timestamp)
        except OverflowError:
            # This happened when a tstamp is year 2000 and
            # a negative time zone was applied, yielding a negative time.
            # Could not reproduce with MicroPython 1.28, so may be this was fixed.
            return "2000-01-01 00:00"
        return f"{t[0]}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"

    def unix_to_esp32( self, timestamp ):
        # ESP32 time is zero on 1/1/2000
        # Unix time is zero on 1/1/1970
        return timestamp - _ESP32_EPOCH
    
    def esp32_to_unix( self, timestamp ):
        return timestamp + _ESP32_EPOCH
    
    # Implement a context manager to set time for a short time
    # Use:
    # with timezone.set_time( temporary_javascript_timestamp ):
    #        do some stuff, for example create a file that has
    #        to have temporary_unix_timestamp as file creation date.
    # Upon exit of the with statement, time will return to normal.

    def set_time( self, temporary_esp32_timestamp ):
        # Store timestamp to be used in __enter__ below
        self.new_timestamp = temporary_esp32_timestamp
        return self
    
    def __enter__( self ):
        # Save stamp in UTC to be able to return to this time on __exit__
        self.saved_stamp = time()
        self._set_rtc( self.new_timestamp )
        return self

    def __exit__( self, _unused_exc_type, _unused_exc_val, _unused_exc_traceback ):
        self._set_rtc( self.saved_stamp )


