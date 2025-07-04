#Copyright (c) 2024 Hermann Paul von Borries
#MIT License

#See https://github.com/mcauser/micropython-mcp23017
#for a full driver.

from micropython import const
from driver_base import BasePin, BaseDriver

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
class MCP23017Driver(BaseDriver):
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
        
        # The MCP23017 operates in bank mode 0 here,
        # i.e. bank 0 uses register+0 and bank 1 uses register+1
        # IOCON is unique, no bank designation needed
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
        
        self.all_notes_off()

    def _write(self, reg, val):
        #assert 0 <= val <= 255
        self._i2c.writeto_mem(
            self._address, reg, (val).to_bytes(1) 
        )
    def _read(self, reg):
        data = self._i2c.readfrom_mem(
            self._address, reg, 1
        )
        return data[0]

    def define_pin( self, *args ):
        return MCPPin( self, *args )
    
    def all_notes_off( self ):
        # Low level "driver level" fast off of all notes
        # Set all outputs to off
        self._write( _MCP_GPIO, 0 )
        self._write( _MCP_GPIO+1, 0 )
    

class MCPPin(BasePin):
    def __init__( self,  driver, pin_number, rank, nominal_midi_note ):
        #assert 0 <= pin_number <= 15

        # Store register number according to bank
        # 0<=pin<8 means bank 0, 8<=pin<=15 means bank 1
        self._gpioreg = _MCP_GPIO + (pin_number//8)
        # Compute bit of this register to be set/reset for this pin
        self._bit = 1<<(pin_number & 0x07)
        super().__init__(driver, pin_number, rank, nominal_midi_note )


    def value( self, val ):
        # Turn this pin on/off according to value
        # The code is  more stable reading the current state from the
        # MCP than caching state in memory.
        r = self._driver._read( self._gpioreg )
        if val:
            self._driver._write( self._gpioreg, r | self._bit )
        else:
            self._driver._write( self._gpioreg, r & (~self._bit) )

    