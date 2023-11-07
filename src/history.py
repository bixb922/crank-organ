import btree
import time
import sys
import gc
if __name__ == "__main__":
    sys.path.append("software/mpy")
from config import config
from timezone import timezone

TIME_ENTRY='DT'
TUNEID_ENTRY='TD'
TUNEID_LEN = 9

# 9 bytes tuneid, yyyy-mm-dd hh:mm = 16 bytes
def encode_time_entry( tuneid, date=None ):
    if date is None:
        date = timezone.now_ymdhm()
    
    assert len(tuneid) == TUNEID_LEN
    assert len(date) == 16
    key = (f"DT,{date},{tuneid}").encode()
    return key

def encode_tuneid_entry( tuneid, date=None ):
    if date is None:
        date = timezone.now_ymdhm()
    assert len(tuneid) == TUNEID_LEN
    assert len(date) == 16
    key = (f"TD,{tuneid},{date}").encode()
    return key

def decode_entry( data ):
    # Always return tuneid, date
    s = data.decode().split(",")
    if s[0] == TUNEID_ENTRY:
        return s[1], s[2]
    elif s[0] == TIME_ENTRY:
        return  s[2], s[1]
    else:
        print("decode entry data=", data, "value error")
        raise ValueError

def tuneid_range( tuneid1, tuneid2=None ):
    if not tuneid2:
        tuneid2 = tuneid1
    first_tuneid = encode_tuneid_entry( tuneid1, "0000-00-00 00:00")
    last_tuneid = encode_tuneid_entry( tuneid2, "9999-99-99 99:99" )
    return first_tuneid, last_tuneid

def time_range( date1, date2 ):
    first_date = encode_time_entry( " "*TUNEID_LEN, date1 )
    last_date = encode_time_entry( chr(126)*TUNEID_LEN, date2 )
    return first_date, last_date


class HistoryManager:
    def __init__( self, filename ):
        try:
            self.file = open( filename, "r+b ")
        except:
            self.file = open( filename, "w+b ")
        gc.collect()
        self.db = btree.open( self.file, cachesize=4*4096 )
    
        
    def add_entry( self, tuneid, percentage, date=None ):
        # Add same entry twice with key ordered
        # by tuneid and key ordered by date.
        key = encode_time_entry( tuneid, date )
        data = bytearray(1)
        data[0] = percentage
        self.db[key] = data
        key = encode_tuneid_entry( tuneid, date  )
        self.db[key] = data
        self.db.flush()
        
    def get_tuneid_count( self, tuneid ):
        n = 0
        for x in self.get_tuneid_events( tuneid ):
            n += 1
        return n
    
    def _get_events( self, key1, key2 ):
        for k, percentage in self.db.items( key1, key2 ):
            tuneid, date = decode_entry( k )
            yield tuneid, date, int.from_bytes( percentage, "big" )
        
    def get_all_events( self ):
        # Sorted by date 
        first_date, last_date = time_range( "0000-00-00 00:00", "9999-99-99 99:99" )
        yield from self._get_events( first_date, last_date )

       
    def get_tuneid_events( self, tuneid ):
        yield from self._get_events( tuneid_range( tuneid ) )
        
    def get_all_tuneid_counts( self ):
        hist = {}
        for tuneid, date, percentage in self.get_all_events():
            if tuneid in hist:
                hist[tuneid] += 1
            else:
                hist[tuneid] = 1
        return hist 


history = HistoryManager( config.HISTORY_DATABASE )

if __name__ == "__main__":
    for k,v in history.db.items():
        print(k, v)
