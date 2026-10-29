#Copyright (c) 2024 Hermann Paul von Borries
#MIT License

# See https://github.com/mcauser/micropython-mcp23017
# for a full driver.

from micropython import const
from driver_sole import SolePin, SoleDriver
from actuatorstats import ActuatorStats

# register addresses in bank=0 mode 
_MCP_IODIR = const(0x00)  # R/W I/O Direction Register
_MCP_IPOL = const(0x02)  # R/W Input Polarity Port Register
_MCP_GPINTEN = const(0x04)  # R/W Interrupt-on-Change Pins
_MCP_DEFVAL = const(0x06)  # R/W Default Value Register
_MCP_INTCON = const(0x08)  # R/W Interrupt-on-Change Control Register
_MCP_IOCON = const(0x0A)  # R/W Configuration Register
_MCP_GPPU = const(0x0C)  # R/W Pull-Up Resistor Register
_MCP_GPIO = const(0x12)  # R/W General Purpose I/O Port Register


# Not a singleton, one instance for each MCP23017 chip
class MCP23017Driver(SoleDriver):
    def __init__( self, i2c, i2c_number, address ):
        super().__init__(  i2c_number, address )

        # i2c is the machine.I2C instance
        self._i2c = i2c
        self._address = address
        # The number is used to identify the I2C bus in __repr__
        self._i2c_number = i2c_number

        # error if device not found at i2c addr
        if self._i2c.scan().count(self._address) == 0:
            raise OSError(
                f"MCP23017 not found at I2C address {address:#x}"
            )
        self._reset()

    def _reset(self):
        # The MCP23017 operates in bank mode 0 here,
        # i.e. bank 0 uses register+0 and bank 1 uses register+1
        # IOCON is unique, no bank designation needed
        for _ in range(5):
            try:
                self._write( _MCP_IOCON, 0 )
                for bank in range(2):
                    # Configure MCP23017 for output
                    self._write( _MCP_IODIR+bank, 0) # Direction: output
                    # After power-on reset, all registers should be zero,
                    # except IODIR, which is set to "input" (all ones)
                    # So it should not be necessary to initialize all these
                    # but let's do it anyways
                    self._write( _MCP_IPOL+bank, 0) # Polarity: normal
                    self._write( _MCP_GPINTEN+bank, 0 ) # Interrupts disabled
                    self._write( _MCP_DEFVAL+bank, 0 )  # Default value for interrupts: 0
                    self._write( _MCP_INTCON+bank, 0 ) # Interrupt-on-change: disabled
                    self._write( _MCP_GPPU+bank, 0 )  # Pull ups disabled (valid only for inputs anyhow)
            except OSError:
                self._i2c.init()
                ActuatorStats.count("MCP23017 reset retries")
        self.fast_off()

    def _write(self, reg, val):
        #self._i2c.writeto_mem(
        #    self._address, reg, (val).to_bytes(1) 
        #)
        #self._i2c.write_byte( self._address, reg, val )
        for i in range(5):
            try:
                if i > 0:
                    self._reset()
                self._i2c.write( self._address, reg, val )
            except OSError:
                self._i2c.init()
                ActuatorStats.count("MCP23017 ENODEV")
        ActuatorStats.count("MCP23017 write fails")

    def _read(self, reg):
        #data = self._i2c.readfrom_mem( self._address, reg, 1)
        #return data[0]
        #return self._i2c.operate( self, self._i2c.read_byte, self._address, reg )
        for i in range(5):
            try:
                if i > 0:
                    self._reset()
                return self._i2c.read_byte( self._address, reg )
            except OSError:
                self._i2c.init()
                ActuatorStats.count("MCP23017 ENODEV")
        raise RuntimeError("MCP23017 read failed")


    def define_pin( self, *args ):
        # Pass this driver and then the *args
        return MCPPin( self, *args )
    
    def fast_off( self ):
        # Low level "driver level" fast off of all notes
        # Set all outputs to off
        self._write( _MCP_GPIO, 0 )
        self._write( _MCP_GPIO+1, 0 )
        # Now BasePin._count is off, fix that
    

class MCPPin(SolePin):
    def __init__( self,  driver, pin_number, rank, nominal_midi_note ):
        #assert 0 <= pin_number <= 15

        # Store register number according to bank
        # 0<=pin<8 means bank 0, 8<=pin<=15 means bank 1
        self._gpioreg = _MCP_GPIO + (pin_number//8)
        # Compute bit of this register to be set/reset for this pin
        self._bit = 1<<(pin_number & 0x07)
        super().__init__(driver, pin_number, rank, nominal_midi_note )

    def low_level_on( self ):
        # It is better reading the current state from the
        # MCP than caching state in memory.
        r = self._driver._read( self._gpioreg )
        self._driver._write( self._gpioreg, r | self._bit )

    def low_level_off( self ):
        r = self._driver._read( self._gpioreg )
        self._driver._write( self._gpioreg, r & (~self._bit) )

    
    