# (c) Copyright 2026 Hermann Paul von Borries
# MIT License

import bluetooth
import struct
from micropython import const

from micropython import const
import struct
import bluetooth

# Advertising packet constants
#_ADV_TYPE_FLAGS = const(0x01)
#_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID16_COMPLETE = const(0x3)
#_ADV_TYPE_UUID32_COMPLETE = const(0x5)
#_ADV_TYPE_UUID128_COMPLETE = const(0x7)

#_ADV_MAX_PAYLOAD = const(31)

# Interrupt constants
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)

_FLAG_READ = const(0x0002)

# >>> show how many users are connected, at least show activity.

# https://devzone.nordicsemi.com/f/nordic-q-a/24170/16bit-uuid-misunderstandings

# Using Media Control Services standard registered UUID
_MCS_UUID = bluetooth.UUID(0x1848)
# Pending: add track title (=tune title) and other info, allow next button.
# Must find a nice BLE app or device.

# Some private UUID
# UUID order and name order must be equivalent to Javascript client
_CHARACTERISTIC_UUIDS = [
    "2a7c3e29-62f9-47bf-8b00-69db8c3c88f1",
    "49f99c64-b2c8-40de-a944-ea4fd48b497a",
    "1732b3cb-c879-4157-a106-65d38cac591b",
    "c9eb91e8-03ca-4739-a774-8fbee561caee",
    "98bfa6b0-55fc-4197-905e-635d68e58bf6",
    "35dcf9be-89be-404b-bb7f-61dde7160e96",
    "b17957bc-c797-470c-b844-6015c9f7f390"
]
# Same order as UUIDs
_CHARACTERISTIC_NAMES = [ "stassid1", "stassid2", "apssid", "staip1", "staip2",  "apip", "status"]
assert len(_CHARACTERISTIC_NAMES) == len(_CHARACTERISTIC_UUIDS)

_SERVICE_DESCRIPTOR = (
    _MCS_UUID,
    ( tuple((bluetooth.UUID(uuid), _FLAG_READ) for uuid in _CHARACTERISTIC_UUIDS ))
)


class BLEMCS:
    def __init__(self, name ):
        self._ble =  bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)
        services = self._ble.gatts_register_services((_SERVICE_DESCRIPTOR,))
        # For easy use make dictionary of handles
        self.handles = dict()
        for i, h in enumerate(services[0]):
            self.handles[_CHARACTERISTIC_NAMES[i]] = h
        #self._connections = set()
        self._payload = self._advertising_payload( name, _MCS_UUID )
        # Write characteristic with initial status
        self.status = bytearray("nnn".encode())
        self.set_status( "sta1", "n" )
        # Random address mode. MACos caches name by physical address
        # making it impossible to change the advertised name later on.
        self._ble.config(addr_mode = 0x01)

    def _irq(self, event, data):
        #if event == _IRQ_CENTRAL_CONNECT:
        #    conn_handle, _, _ = data
        #    self._connections.add(conn_handle)
        if event == _IRQ_CENTRAL_DISCONNECT:
            # conn_handle, _, _ = data
            # if conn_handle in self._connections:
            #    self._connections.remove(conn_handle)
            # Start advertising again to allow a new connection.
            self.start_advertising()

    # Generate a payload to be passed to gap_advertise(adv_data=...).
    # Maximum length of name must be 15 bytes to fit into packet.
    def _advertising_payload(self, name, uuid ):
        def _append(adv_type, value):
            nonlocal payload
            payload += struct.pack("BB", len(value) + 1, adv_type) + value

        print(f"BLEMCS Advertise {name=}, service {uuid=}")
        payload = bytearray()
        _append(0x01, struct.pack("B", 0x06)) # Flags: General Discoverable, LE only
        _append(0x09, name[0:15].encode()) # limit length
        _append(_ADV_TYPE_UUID16_COMPLETE, bytes(uuid)) # 32-bit complete Service UUIDs
        return payload
    
    def set_characteristic( self, char_name, value ):
        self._ble.gatts_write(self.handles[char_name], value.encode())

    def set_status( self, net, new_status ):
        n = ["sta1", "sta2", "ap"].index(net)
        self.status[n] = ord(new_status)
        self._ble.gatts_write(self.handles["status"], self.status )
        
    def start_advertising( self ):
        # Ensure address is random to avoid caching of advertised name
        self._ble.config(addr_mode = 0x01)
        self._ble.gap_advertise(500_000, adv_data=self._payload) # type:ignore
        
    
class BLEnull:
    # Empty BlEMCS() if Bluetooth is not configured.
    def __getattr__( self, _ ):
        return lambda *args: None
        

#def demo():
#    from random import randrange
#    mcs = BLEMCS("orgelinchen")
#    mcs.set_characteristic( "stassid1", "STA 1 SSID")
#    mcs.set_characteristic( "stassid2", "STA 2 SSID")
#    mcs.set_characteristic( "apssid", "AP SSID")
#    mcs.set_characteristic( "staip1", "192.168.100.111")
#    mcs.set_characteristic( "staip2", "192.168.100.222")
#    mcs.set_characteristic( "apip", "192.168.100.333")
#    mcs.start_advertising()
#    
#    i = 0
#    while True:
#        print(f"{i} {mcs._connections=}")
#        time.sleep(1)
#        i +=1
#        
#if __name__ == "__main__":
#    demo()