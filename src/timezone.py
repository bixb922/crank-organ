# (c) 2023 Hermann Paul von Borries
# MIT License
import sys
import time
import ntptime
import asyncio
import machine

import scheduler
import fileops

TZFILE = "data/timezone.json"
RETRIES = 5


class TimeZone:
    def __init__(self):
        self.ntp_task = None
        self.logger = None
        # No logger yet, because of import circularity

        tz = fileops.read_json( TZFILE, {} )
        if not tz or "longName" not in tz:
            self.offset = 0
            self.shortName = self.longName = "UTC"
        else:
            self.offset = tz["offset"]
            self.shortName = tz["shortName"]
            self.longName = tz["longName"]


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
        if time.time() > 756864000: # time after 2024/1/1?
            return # Clock already set
        try:
            await self._get_ntp_time()
        except Exception as e:
            self.logger.exc(e, "Could not get ntp time")
            return
        
        # Now we have local time, apply stored time zone only once.
        # Prepare a time tuple as argument for RTC
        t = time.localtime(time.time() - self.offset )
        # Set this as the local time, to be returned
        # by time.localtime() and time.time()
        # year, month, day, weekday, hour, minute, second, subsecond
        machine.RTC().datetime( (t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))

 
    async def _get_ntp_time(self):
        # Retry a few times.
        retry_time = 2000
        for _ in range(RETRIES):
            try:
                async with scheduler.RequestSlice("ntptime", 1000):
                    # ntptime.settime is not async, will block
                    # Could launch in separate thread...?
                    ntptime.settime()
                return 
            except (asyncio.TimeoutError, OSError) as e:
                self.logger.info(f"Recoverable ntptime exception {repr(e)}")
                # RequestSlice did not give slice, retry later
                # OSError -202 means server not found, happens once in a while
                pass
            except Exception as e:
                self.logger.info(f"Unrecoverable ntptime exception {repr(e)}")
                return

            await asyncio.sleep_ms(retry_time)
            # ntp servers don't like frequent retries...
            # After first retry, duplicate retry time for each time
            retry_time *= 2

    def set_time_zone( self, newtz ):
        # Called from webserver with /set_time_zone
        # Which in turn is called from common.js for each hard page load
        # Takes effect at next reboot. Needs a hard reset for RTC time to
        # get rid of time zone. Soft resets don't reset to zero and the offset
        # gets lost on reboot.
        if newtz["offset"] == self.offset:
            # Optimization to avoid writing file.
            return
        self.offset = newtz["offset"]
        self.shortName = newtz["shortName"]
        self.longName = newtz["longName"]
        fileops.write_json( newtz, TZFILE, keep_backup=False )

        self.logger.info("Timezone info updated, takes effect next reboot")

    def get_time_zone_info( self ):
        return (self.offset, self.shortName, self.longName)
    
    def now_timestamp(self):
        # time.time() is already in local time, no need to add offset
        return time.time() 
    
    def now(self):
        t = time.localtime(self.now_timestamp())
        if t[0] < 2010:
            # Don't apply time zone if no clock set (no ntptime yet)
            return time.localtime()
        return t

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
        t = self.now()
        if t[0] < 2010:
            # No ntptime (yet)
            return self.now_hms()
        else:
            return self.now_ymdhms() + self.shortName

    def _log_exception(self, e, message):
        print(message, e)
        sys.print_exception(e)
        
timezone = TimeZone()
