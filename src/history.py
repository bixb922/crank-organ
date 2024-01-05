# (c) 2023 Hermann Paul von Borries
# MIT License

import btree
import gc

# if __name__ == "__main__":
#    sys.path.append("software/mpy")
from config import config
from timezone import timezone
from minilog import getLogger

TIME_ENTRY = "DT"
TUNEID_ENTRY = "TD"
TUNEID_LEN = 9


# 9 bytes tuneid, yyyy-mm-dd hh:mm = 16 bytes
def encode_time_entry(tuneid, date=None):
    # Make the key for time-sorted record
    if date is None:
        date = timezone.now_ymdhm()

    assert len(tuneid) == TUNEID_LEN
    assert len(date) == 16
    key = (f"DT,{date},{tuneid}").encode()
    return key


def encode_tuneid_entry(tuneid, date=None):
    # Make key for tune-sorted record
    if date is None:
        date = timezone.now_ymdhm()
    assert len(tuneid) == TUNEID_LEN
    assert len(date) == 16
    key = (f"TD,{tuneid},{date}").encode()
    return key


def decode_entry(data):
    # Decode the key
    # Always return tuneid, date
    s = data.decode().split(",")
    if s[0] == TUNEID_ENTRY:
        return s[1], s[2]
    elif s[0] == TIME_ENTRY:
        return s[2], s[1]
    else:
        print("decode entry data=", data, "value error")
        raise ValueError


def tuneid_range(tuneid):
    # Make a range for one tuneid
    first_tuneid = encode_tuneid_entry(tuneid, "0000-00-00 00:00")
    last_tuneid = encode_tuneid_entry(tuneid, "9999-99-99 99:99")
    return first_tuneid, last_tuneid


def time_range(date1, date2):
    # Make a range by date
    first_date = encode_time_entry(" " * TUNEID_LEN, date1)
    last_date = encode_time_entry(chr(126) * TUNEID_LEN, date2)
    return first_date, last_date


class HistoryManager:
    def __init__(self, filename):
        self.logger = getLogger(__name__)
        try:
            self.file = open(filename, "r+b ")
        except OSError:
            self.file = open(filename, "w+b ")
        gc.collect()
        self.db = btree.open(self.file, cachesize=4 * 4096)
        self.logger.debug("init ok")

    def add_entry(self, tuneid, percentage, requested):
        # This can take 1 second
        # Add same entry twice, once with key ordered
        # by tuneid and once with key ordered by date.
        data = bytearray(2)
        data[0] = percentage
        data[1] = 1 if requested else 0
        key = encode_time_entry(tuneid)
        self.db[key] = data
        key = encode_tuneid_entry(tuneid)
        self.db[key] = data
        self.db.flush()

    def get_tuneid_count(self, tuneid):
        # Count all occurrences of one tuneid
        n = 0
        for x in self._get_tuneid_events(tuneid):
            n += 1
        return n

    def _get_events(self, key1, key2):
        # Get events in a range of keys.
        # use tuneid_range() or time_range() to
        # make the keys
        for k, data in self.db.items(key1, key2):
            percentage = data[0]
            requested = False
            if len(data) > 1:
                requested = data[1] != 0
            tuneid, date = decode_entry(k)
            yield tuneid, date, percentage, requested

    def get_all_events(self):
        # Sorted by date
        first_date, last_date = time_range(
            "0000-00-00 00:00", "9999-99-99 99:99"
        )
        yield from self._get_events(first_date, last_date)

    def _get_tuneid_events(self, tuneid):
        yield from self._get_events(*tuneid_range(tuneid))

    def delete_old(self, months):
        if months < 0:
            raise ValueError("Months must be >= 0")
        # purge history
        now = timezone.now_ymd()
        # 0000-00-00
        # 0....5..8
        year = int(now[0:4])
        month = int(now[5:7])
        day = int(now[8:])
        month -= months
        while month < 1:
            year -= 1
            month += 12
        ymd = f"{year:4d}-{month:02d}-{day:02d} 00:00"
        k1, k2 = time_range("0000-00-00 00:00", ymd)
        n = 0
        for tuneid, date, _ in self._get_events(k1, k2):
            key1 = encode_tuneid_entry(tuneid, date)
            key2 = encode_time_entry(tuneid, date)
            for k in (key1, key2):
                try:
                    del self.db[k]
                except Exception as e:
                    self.logger.exc(e, f"could not delete history {k=}")
            n += 1
        self.logger.info(f"{n} history entries deleted")
        self.db.flush()

    def get_all_tuneid_counts(self):
        hist = {}
        for tuneid, date, data in self.get_all_events():
            if tuneid in hist:
                hist[tuneid] += 1
            else:
                hist[tuneid] = 1
        return hist


history = HistoryManager(config.HISTORY_DATABASE)

# if __name__ == "__main__":
#    history.add_entry( "isqgaMYPA", 33 )
#    history.add_entry( "iKnrPo9uf", 44 )
#    history.add_entry( "iDpKbWgZr", 55 )
#    for k,v in history.db.items():
#        if "2000" in k:
#            print(k, v)
#    history.delete_old( 3 )
#    for k,v in history.db.items():
#        if "2000" in k:
#            print(k, v)
