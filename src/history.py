# (c) Copyright 2023-2025 Hermann Paul von Borries
# MIT License

from drehorgel import timezone
import minilog
import fileops

class HistoryManager:
    def __init__(self, history_json):
        self.history_json = history_json
        self.logger = minilog.getLogger(__name__)
        self.logger.debug("init ok")
        # Check if history is present, create empty if not 
        # Creating the history early on allows browser to
        # read data/history.json directly.
        if not fileops.file_exists( self.history_json ):
            fileops.write_json( [], self.history_json )

    def _read_hlist(self):
        # Read json, recreate if error.
        hlist = fileops.read_json(self.history_json,
                                  default=[],
                                  recreate=True)
        self.logger.debug(f"{len(hlist)} elements in history")
        return hlist
    
    def add_entry( self, tuneid, start_time, percentage, requested ):     
        hlist = self._read_hlist()
        # use 1/0 instead of true/false to save space
        # use timestamp instead of full ascii date to 
        # make time comparison in self.delete_old() easier.
        hlist.append((tuneid, start_time, percentage, 1 if requested else 0 ))
        fileops.write_json(hlist, self.history_json, keep_backup=False)

    def delete_old(self, days):
        # purge indicated number of days of history
        if days < 0:
            raise ValueError("Days must be >= 0")
        # Calculate cutoff date
        cutoff = timezone.now_timestamp()-(days*24*3600)
        history_list = self._read_hlist()
        # Count how many elements have to be deleted
        n = sum( 1 for x in history_list if x[1]<cutoff )
        self.logger.info(f"Purge {n} oldest elements in history")
        # Now delete list elements that are too old,
        # delete the n elements at the start of hlist
        for _ in range(n):
            del history_list[0]
        fileops.write_json( history_list, self.history_json )


