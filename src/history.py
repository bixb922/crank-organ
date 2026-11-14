# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License
import time, asyncio

from drehorgel import timezone, config
import fileops, scheduler
from minilog import getLogger

_SECONDS_PER_DAY = const(24*3600)

class HistoryManager:
    def __init__(self):
        self.logger = getLogger(__name__)
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
        # self.logger.debug(f"{len(hlist)} elements in history")
        return hlist
    
    def add_entry( self, tuneid, start_time, percentage, repeat_count ):  
        hlist = self._read_hlist()
        # use 1/0 instead of true/false to save space
        # use timestamp instead of full ascii date to 
        # make time comparison in self.delete_old() easier.
        hlist.append((tuneid, start_time, percentage, repeat_count ))
        fileops.write_json(hlist, config.HISTORY_JSON, keep_backup=False)
        hlist = None
        
    def delete_old(self, days):
        # purge indicated number of days of history going back from now (not midnight)
        cutoff = time.time()-(days*_SECONDS_PER_DAY)
        self._delete( lambda h: h[1]<cutoff )

    def delete_date( self, start, end):
        self._delete( lambda h: start <= h[1] <= end)

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
