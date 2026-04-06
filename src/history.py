# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
import time, asyncio

from drehorgel import timezone, config
import minilog, fileops, scheduler

_SECONDS_PER_DAY = const(24*3600)

class HistoryManager:
    def __init__(self):
        self.logger = minilog.getLogger(__name__)
        self.logger.debug("init ok")
        # Creating the history early on allows browser to
        # read data/history.json directly.
        if not fileops.file_exists( config.HISTORY_JSON ):
            fileops.write_json( [], config.HISTORY_JSON )
        asyncio.create_task( self.purge_history() )

    def _read_hlist(self):
        # Read json, recreate if error.
        hlist = fileops.read_json(config.HISTORY_JSON,
                                  default=[],
                                  recreate=True)
        self.logger.debug(f"{len(hlist)} elements in history")
        return hlist
    
    def add_entry( self, tuneid, start_time, percentage, rfu ):     
        hlist = self._read_hlist()
        # use 1/0 instead of true/false to save space
        # use timestamp instead of full ascii date to 
        # make time comparison in self.delete_old() easier.
        hlist.append((tuneid, start_time, percentage, 1 if rfu else 0 ))
        fileops.write_json(hlist, config.HISTORY_JSON, keep_backup=False)
        hlist = None
        
    def delete_old(self, days):
        # purge indicated number of days of history
        cutoff = timezone.now_timestamp()-(days*_SECONDS_PER_DAY)
        self._delete( lambda h: h[1]<cutoff )

    def delete_date( self, yyyy_mm_dd ):
        year, month,day = yyyy_mm_dd.split("-")
        t = time.mktime( (int(year),int(month),int(day),0,0,0,0,0) )
        start = int(t/_SECONDS_PER_DAY)*_SECONDS_PER_DAY
        end = start + _SECONDS_PER_DAY
        highest_date = 1000*365*_SECONDS_PER_DAY # about 1000 years in the future
        self._delete( lambda h: (start <= h[1] < end) or h[1] > highest_date )

    def _delete( self, delete_fn ):
        # Delete entries where delete_fn(entry) is True
        history_list = self._read_hlist()
        newlist = [ h for h in history_list if not delete_fn(h) ]
        self.logger.info(f"Delete history entries, removed {len(history_list)-len(newlist)} entries")
        fileops.write_json( newlist, config.HISTORY_JSON )

    async def purge_history( self ):
        days = config.auto_purge_history
        if days:
            await scheduler.wait_for_player_inactive()
            self.delete_old( days )
