#Copyright (c) 2024 Hermann Paul von Borries
#MIT License

import ustruct
import time


from driver_base import BasePin, BaseDriver

# >>> angle calculator in pinout page

#  one instance for each PCA chip
class PCA9685Driver(BaseDriver):
    def __init__(self, i2c, i2c_number, address, period_us):
        print("calling super init")
        super().__init__(  i2c_number, address )

        self.i2c = i2c
        self.address = address
        self.period_us = period_us

        if i2c.scan().count(address) == 0:
            raise OSError(
                f"PCA8685 not found at I2C address {address:#x}"
            )
        self.pca = PCA9685(i2c, address, period_us)
        self.pin_list = [] 

    def set_servopulse( self, pulse0_us, pulse1_us ):
        if not( 600 <= pulse0_us <= 2400 and
                600 <= pulse1_us <= 2400 ):
            raise ValueError("Pulse width not 600 to 2400")
        # Store temporarily here. This is
        # valid for define_pin() calls done until next set_servopulse()
        self.pulse0_us = pulse0_us
        self.pulse1_us = pulse1_us 

    def define_pin( self, *args ):
        sp = PCAPin( self,  *args )
        sp.set_device( self.pca, self.period_us, self.pulse0_us, self.pulse1_us )
        self.pin_list.append( sp )
        return sp
    
    def all_notes_off( self ):
        # No shorter way to do this, since pulse0_us can be potentially
        # different for each pin, so we cannot just set all to some value.
        for sp in self.pin_list:
            sp.value(0)
    
class PCAPin(BasePin):

    def set_device( self, pca, period_us, pulse0_us, pulse1_us ):
        self.pca = pca
        # self._pulse_on = PCA count (0-4095) when the pulse has to start 
        # self._pulse_offx = PCA count (0-4095) when the pulse has to stop, x in [0,1]
        # It is valid if off is smaller than on (i.e. the pulse times operate
        # modulo 4096)

        # Stagger the start of the pulses, perhaps it
        # makes that the total current a bit lower 
        self._pulse_on = round(self._pin/16*4096)
        # Calculate pulse end for 0 
        length0 = round(pulse0_us/period_us*4096)
        self._pulse_off0 = (self._pulse_on + length0) % 4096
        
        # Calculate pulse end for 1
        length1 = round(pulse1_us/period_us*4096)
        self._pulse_off1 = (self._pulse_on + length1) % 4096
        
    def value( self, val ):
        self.pca.set_pwm( self._pin, self._pulse_on, self._pulse_off1 if val else self._pulse_off0 )
 
# Low level driver
# Derived from 
# https://github.com/mcauser/deshipu-micropython-pca9685
# https://github.com/pappavis/micropython-pca9685/blob/main/pca9685/servo.py
class PCA9685:
    def __init__(self, i2c, address, period_us):
        self.i2c = i2c
        self.address = address
        self.period_us = period_us

        self._reset()
        # Frequency is the same for all outputs.
        self._freq( 1_000_000/period_us )

    def _write(self, address, value):
        self.i2c.writeto_mem(self.address, address, bytearray([value]))

    def _read(self, address):
        return self.i2c.readfrom_mem(self.address, address, 1)[0]

    def _reset(self):
        self._write(0x00, 0x00) # Mode1

    def _freq(self, freq=None):
        if freq is None:
            return int(25000000.0 / 4096 / (self._read(0xfe) - 0.5))
        prescale = int(25000000.0 / 4096.0 / freq + 0.5)
        old_mode = self._read(0x00) # Mode 1
        self._write(0x00, (old_mode & 0x7F) | 0x10) # Mode 1, sleep
        self._write(0xfe, prescale) # Prescale
        self._write(0x00, old_mode) # Mode 1
        time.sleep_us(5)
        self._write(0x00, old_mode | 0xa1) # Mode 1, autoincrement on
        
    
    def set_pwm(self, index, on, off):
        # on=time to turn on the pulse, off=time to turn off the pulse
        data = ustruct.pack('<HH', on, off)
        self.i2c.writeto_mem(self.address, 0x06 + 4 * index,  data)

    # def get_pwm( self, index ):
    #     data = self.i2c.readfrom_mem(self.address, 0x06 + 4 * index, 4)
    #     return ustruct.unpack('<HH', data)
