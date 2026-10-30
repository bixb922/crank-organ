from machine import Pin, SoftI2C
from minilog import getLogger
from actuatorstats import ActuatorStats

I2C_RETRIES=const(5)
TEST_I2C_PINS = True

# from random import random
# TEST_I2C_PINS = False
# class SoftI2C:
#     num = -1
#     def __init__( self, sclpin, sdapin, freq=100_000):
#         SoftI2C.num += 1
#         print(f">>>test mock SoftI2C {SoftI2C.num} {sclpin} {sdapin} (simulated)************")
#         pass

#     def writeto_mem(self, address, register, data):
#         if random()>0.95:
#             print(f">>>******I2C {SoftI2C.num} raise OSError")
#             raise OSError
#         print(f">>>softi2c {SoftI2C.num} writeto_mem {address:2d} {register:2d} {data}" )
#         pass

#     def readfrom_mem( self, address, register, length ):
#         if random()>0.95:
#             print(f">>>******I2c {SoftI2C.num} raise OSError")
#             raise OSError
#         print(f">>>softi2c {SoftI2C.num} readfrom_mem {address:2d} {register:2d} {length:2d}")
#         return b'\x00\x00\x00\x00'[0:length]

#     def scan(self):
#         if random()>0.95:
#             print(f">>>***i2c {SoftI2C.num} scan error, scan returns empty" )
#             return []
#         return [32,33,64,65]
    
# One instance for each I2C bus, i.e. for each SCL/SDA pair
class I2Cdriver:
    def __init__( self, i2c_number, scl, sda, freq ):
        self.i2c_number = i2c_number
        self.scl = scl
        self.sda = sda
        self.freq = freq # in kHz
        self.logger = getLogger(__name__)
        self.devices = set()
        from solenoid import PinTest
        if TEST_I2C_PINS and not PinTest.testI2Cconnected(sda, scl):
            raise RuntimeError(f"{self} pin test failed")
        
        self.init()

    def init(self):
        self.i2c = SoftI2C(Pin(self.scl), Pin(self.sda), freq=self.freq)

    #def writeto_mem(self, address, register, data ):
    # superceded by write()
    #    self.i2c.writeto_mem(address, register, data)

    def read_byte(self, address, register ):
        return self.i2c.readfrom_mem(address, register, 1)[0]

    #def write_byte( self, address, register, value):
    # superceded by write()
    #    self.i2c.writeto_mem(
    #                 address, register, (value).to_bytes(1) )


    def write( self, address, register, value):
        if type(value) is int:
            self.i2c.writeto_mem(address, register, (value).to_bytes(1))
        else:
            self.i2c.writeto_mem(address, register, value)

    def with_retries(self, driver, method, *args):
        # do an I2C operation method(*args) with retries
        # driver: this is the calling driver
        for i in range(I2C_RETRIES):
            if i > 0 and not method.__name__.startswith("reset"):
                # Avoid recurring, don't reset if method is reset
                self.reset_all()
            try:
                return method(*args)
            except OSError:
                self.logger.async_info(f"I2C ENODEV error {driver} {method.__name__} args={args} retry={i}")
                ActuatorStats.count(f"ENODEV retries")
        ActuatorStats.count(f"ENODEV failed")
        raise RuntimeError(f"{driver} operation failed (ENODEV)")

    def reset_all(self):
        # Reset all devices on the I2C bus, retry complete reset
        # if ENODEV failure is found.
        def reset_all_process():
            self.init()
            for drv in self.devices:
                drv.reset(self)
        # Do all retries of all devices atomically
        self.with_retries(self, reset_all_process)

    def __repr__(self):
        return f"I2C({self.i2c_number})"