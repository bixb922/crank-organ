# (c) 2023 Hermann Paul von Borries
# MIT License
import sys
import time

import ntptime
import asyncio

import scheduler
import aiohttp

import fileops

TZFILE = "data/timezone.json"
RETRIES = 10


class TimeZone:
    # Get time zone information once a day at most from worldtimeapi.org.
    # Provide formatted local time functions.
    def __init__(self):
        # Start with a default time zone
        self.tz = {
            "offset_sec": 0,
            "next_refresh": "0000-00-00",
            "abbreviation": "UTC",
        }

        self.timezone_task_active = False
        try:
            self.tz = fileops.read_json(TZFILE)
        except (OSError, ValueError) as e:
            print(f"timezone - Could not read timezone.json: {e}")
            pass
        # No logger yet, timezone is prerrequisite for minilog
        self.logger = None

    def setLogger(self,getLogger):
        self.logger = getLogger(__name__)
        
    def network_up(self):
        # wifimanager calls here when network is up
        if self.timezone_task_active:
            # Avoid reentering task while active
            return
        self.timezone_task_active = True

        self.timezone_task = asyncio.create_task(self._timezone_process())

    async def _timezone_process(self):
        # Get ntp time, then update time zone
        await self._get_ntp_time()

        await self._update_time_zone()
        self.timezone_task_active = False

    async def _get_ntp_time(self):
        if time.localtime()[0] >= 2023:
            # Time already set
            return
        # Retry a few times.
        retry_time = 2000
        for _ in range(RETRIES):
            try:
                async with scheduler.RequestSlice("ntptime", 1000):
                    # settime is not async, will block
                    # Can't do this with worldtimeapi, should not call frequently
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
            retry_time = 70_000 # ntp servers don't like frequent retries...

    async def _update_time_zone(self):
        ft = self.now_ymd()
        if ft < self.tz["next_refresh"]:
            # Don't ask every day
            return
        for _ in range(RETRIES):
            try:
                # If network is working, response takes 350 msec
                # Using RequestSlice is really not relevant since
                # get_time_zone is async non blocking. But
                # just in case protect the playing...
                async with scheduler.RequestSlice("timezone", 1000):
                    await self.get_time_zone()
                return
            except asyncio.TimeoutError as e:
                # RequestSlice signaled busy, try later
                self.logger.info("RequestSlice timeout waiting for time zone server")
                pass
            except OSError as e:
                # e.errno == -202 No network connection
                # e.errno == 118 EHOSTUNREACH
                # Retry
                self.logger.info(f"Exception calling get_time_zone {e}")
                pass
            except Exception as e:
                self.logger.exc(
                    e, "unrecoverable exception in get time zone"
                )
                return
            self.logger.info("error in get time zone, retry")
            await asyncio.sleep_ms(10_000)

    def write_timezone_file(self):
        self._get_next_refresh_date()
        fileops.write_json( self.tz, TZFILE, keep_backup=False )

    async def get_time_zone(self):
        
        from config import config
        url = "http://worldtimeapi.org/api/timezone/" + config.cfg["tzidentifier"]
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return
                resp = await response.json()
        if "error" in resp:
            self.logger.error(f"Error in get_time_zone: {resp}")
            return

        # Get offsets to compute net offset
        dst_offset = int(resp.get("dst_offset", 0))
        raw_offset = int(resp.get("raw_offset", 0))

        # Cache offset and abbreviation in flash until next
        # refresh (i.e. at least 1 day). If no network next day
        # information is cached. But if no network, then there is
        # no ntptime too, so that's not so bad
        # Result is in seconds
        new_offset = dst_offset + raw_offset
        new_abbreviation = resp.get("abbreviation", "")
        self.tz["offset_sec"] = new_offset
        self.tz["abbreviation"] = new_abbreviation
        # Store for future reboots. Store always to avoid
        # frequent refresh
        self.write_timezone_file()
        self.logger.info("Timezone info updated")
            

    def _get_next_refresh_date(self):
        t = self.now()
        if t[0] < 2023:
            # No refresh date if no date set
            return

        # Refresh when the day has changed.
        # Note that "2023-11-01" > "2023-10-32"
        self.tz["next_refresh"] = f"{t[0]}-{t[1]:02d}-{t[2]+1:02d}"

    def now_timestamp(self):
        return time.time() + self.tz["offset_sec"]
    
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
            return self.now_ymdhms() + self.tz["abbreviation"]

    def _log_exception(self, e, message):
        print(message, e)
        sys.print_exception(e)


timezone = TimeZone()


# if __name__ == "__main__":
#    # Test
#    import network
#    # For test, move next line to beginning of program
#    sys.path.append( "/software/mpy")
#
#    def print_now():
#        print(f"{timezone.now_ymdhms()=}")
#        print(f"{timezone.now_ymdhm()=}")
#        print(f"{timezone.now_hms()=}")
#        print(f"{timezone.now_ymd()=}")
#        print(f"{timezone.now_ymdhmsz()=}")
#        print("")
#
#    async def do_connect():
#        print_now()
#        print("do_connect")
#        sta_if = network.WLAN(network.STA_IF)
#        sta_if.active(False)
#
#        if not sta_if.isconnected():
#            print('connecting to network...')
#            sta_if.active(True)
#            sta_if.connect('magus-2.4G', 'apfelstrudel514')
#            while not sta_if.isconnected():
#                await asyncio.sleep_ms(1)
#
#        print('network config:', sta_if.ifconfig())
#        timezone.network_up()
#        await asyncio.sleep(1)
#
#        print_now()
#        await asyncio.sleep(1)
#        await asyncio.sleep(5)
#        print_now()
#        print("Test ended")
#
#    def main():
#        await do_connect()
#        await asyncio.sleep(10000)
#    asyncio.run(main())

# Sample json returned by worldtimeapi.org
# dst_from, dst_until are shown only when dst is true.
# {
#  "abbreviation": "-03",
#  "client_ip": "2800:300:6331:8190::2",
#  "datetime": "2023-10-21T23:43:25.445175-03:00",
#  "day_of_week": 6,
#  "day_of_year": 294,
#  "dst": true,
#  "dst_from": "2023-09-03T04:00:00+00:00",
#  "dst_offset": 3600,
#  "dst_until": "2024-04-07T03:00:00+00:00",
#  "raw_offset": -14400,
#  "timezone": "America/Santiago",
#  "unixtime": 1697942605,
#  "utc_datetime": "2023-10-22T02:43:25.445175+00:00",
#  "utc_offset": "-03:00",
#  "week_number": 42
# }
