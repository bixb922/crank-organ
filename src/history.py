# (c) 2023 Hermann Paul von Borries
# MIT License
import time

from config import config
from timezone import timezone
from minilog import getLogger
import fileops

class HistoryManager:
    def __init__(self,filename):
        self.filename = filename
        self.logger = getLogger(__name__)
        self.logger.debug("init done")
        # Check if history is present, create empty if no backup
        self._read_hlist()

    def _read_hlist(self):
        try:
            hlist = fileops.read_json(self.filename)
        except (OSError,ValueError):
            self.logger.debug(f"Error reading {self.filename}")
            # File not present/readable, backup not present/readable
            hlist = []
            fileops.write_json(hlist, self.filename)
        self.logger.debug(f"{len(hlist)} elements in history")
        return hlist
    
    def add_entry( self, tuneid, percentage, requested ):     
        hlist = self._read_hlist()

        hlist.append((tuneid, timezone.now_timestamp(), percentage, requested ))
        # Write with backup
        fileops.write_json(hlist, self.filename)

    def get_events(self):
        # Iterate through events
        for tuneid,timestamp,percentage,requested in self._read_hlist():
            t = time.localtime(timestamp)
            ft = f"{t[0]:4d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}"
            yield tuneid, ft, percentage, requested

    def delete_old(self, days):
        # purge history
        if days < 0:
            raise ValueError("Days must be >= 0")
        # Calculate cutoff date
        cutoff = timezone.now_timestamp()-(days*24*3600)
        for_deletion = []
        n = 0
        hlist = self._read_hlist()
        for x in hlist:
            if x[1]<cutoff:
                for_deletion.append(n)
        self.logger.info(f"Purge {len(for_deletion)} oldest elements in history")
        # Now delete list elements that are too old, go from end to 
        # beginning of hlist
        for_deletion.reverse()
        for p in for_deletion:
            del hlist[p]
        fileops.write_json( hlist, self.filename )

history = HistoryManager(config.HISTORY_JSON)


