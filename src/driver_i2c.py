from machine import SoftI2C, Pin

class I2Cdriver:
    def __init__( self, scl, sda, freq):
        self.scl = scl
        self.sda = sda
        self.freq = freq # in kHz
        self.init()

    def init(self):
        self.i2c = SoftI2C(Pin(self.scl), Pin(self.sda), freq=self.freq)

    #def writeto_mem(self, address, register, data ):
    #    self.i2c.writeto_mem(address, register, data)

    def read_byte(self, address, register ):
        return self.i2c.readfrom_mem(address, register, 1)[0]

    #def write_byte( self, address, register, value):
    #    self.i2c.writeto_mem(
    #                 address, register, (value).to_bytes(1) )

    def write( self, address, register, value):
        if type(value) is int:
            self.i2c.writeto_mem(address, register, (value).to_bytes(1))
        else:
            self.i2c.writeto_mem(address, register, value)

    # def operate(self, method, *args):
    #     for i in range(6):
    #         try:
    #             return method(*args)
    #         except OSError:
    #             self.logger.async_info(f"I2C ENODEV {self.scl=} {self.sda=} {method.__name__} args={args} retry={i}")
    #             self.init()
    #             raise # Raise will cause caller to do self._reset() and retry.
    #     raise RuntimeError("I2C operation failed")
    
    def scan(self):
        return self.i2c.scan()

    def __repr__(self):
        return f"SoftI2C(scl={self.scl}, sda={self.sda}, freq={self.freq})"