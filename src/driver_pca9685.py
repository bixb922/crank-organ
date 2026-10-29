#Copyright (c) 2024 Hermann Paul von Borries
#MIT License

import ustruct
from time import sleep_us

from driver_rcservo import RCServoPin, RCServoDriver
from actuatorstats import ActuatorStats

# one instance for each PCA chip i.e. one instance for 16 outputs
class PCA9685Driver(RCServoDriver):
    def __init__(self, i2c, i2c_number, address, period_us):
        # period_us is the same for all pins of a PCA9685.
        super().__init__(  i2c_number, address )

        self._i2c = i2c
        self._address = address
        self._period_us = period_us
        # It would be slightly faster with just reading 1 byte at "address"
        # successful i2c.scan() takes about 16msec per board
        # since this is only once at startup, there is no need to optimize.
        if i2c.scan().count(address) == 0:
            raise OSError(
                f"PCA9685 not found at I2C address {address:#x}"
            )
        # Frequency is the same for all outputs.
        self._pwmfreq =  1_000_000/period_us 
        self._reset()

    def define_pin( self, *args ):
        return PCAServoPin( self._period_us,  self, *args )

    def _write(self, register, value):
        #self.i2c.write_byte( self.address, register, value)
        #self.i2c.writeto_mem(self.address, regiregisterster_address, bytearray([value]))
        #self.i2c.operate( self, self.i2c.write_byte, self.address, register, value)
        for i in range(5):
            try:
                if i > 0:
                    self._reset()
                # i2c.write() handles both int and buffer as value.
                return self._i2c.write( self._address, register, value )
            except OSError:
                self._i2c.init()
                ActuatorStats.count("PCA9685 ENODEV")
        ActuatorStats.count("PCA9685 write fails")

    def _read(self, register):
        #return self.i2c.readfrom_mem(self.address, register_address, 1)[0]
        #return self.i2c.read_byte( self.address, register)
        #return self.i2c.operate( self, self.i2c.read_byte, self.address, register)
        for i in range(5):
            try:
                if i > 0:
                    self._reset()
                return self._i2c.read_byte( self._address, register )
            except OSError:
                self._i2c.init()
                ActuatorStats.count("PCA9685 ENODEV")
        raise RuntimeError("PCA9685 read failed")
    
    def _reset(self):
        addr = self._address
        for _ in range(5):
            # Use low level method for read/write and retry complete
            # operation
            try:
                self._i2c.write(addr, 0x00, 0x00) # Mode1
                prescale = int(25000000.0 / 4096.0 / self._pwmfreq + 0.5)
                old_mode = self._i2c.read(addr, 0x00) # Mode 1
                self._i2c.write(addr, 0x00, (old_mode & 0x7F) | 0x10) # Mode 1, sleep
                self._i2c.write(addr, 0xfe, prescale) # Prescale
                self._i2c.write(addr, 0x00, old_mode) # Mode 1
                sleep_us(5) # See datasheet.
                self._i2c.write(addr, 0x00, old_mode | 0xa1) # Mode 1, autoincrement on
                return
            except OSError:
                self._i2c.init()
                ActuatorStats.count("PCA9685 reset retries")
            raise RuntimeError("Could not initialize PCA9685")

    def set_pwm(self, index, start, stop):
        # index=pin number 0-15
        # start=time to start the pulse
        # stop=time to stop the pulse
        # both on a scale of 0 to 4095. 
        # Write in one go.
        data = ustruct.pack('<HH', start, stop)
        #self.i2c.writeto_mem(self.address, 0x06 + 4 * index,  data)
        self._write( 0x06 + 4 * index,  data)


class PCAServoPin(RCServoPin):
    def low_level_on( self ):
        self._driver.set_pwm( self._pin, self._pulse_start, self._1_pulse_stop )
       
    def low_level_off( self ):
        self._driver.set_pwm( self._pin, self._pulse_start, self._0_pulse_stop )
        


    def set_servopulse( self, pulse0_us, pulse1_us ):
        # Validate pulse0_us and pulse1_us
        super().set_servopulse( pulse0_us, pulse1_us )
        # Calculate "on" and "off" settings for a PCA9685.
        # self._pulse_start = PCA count (0-4095) when the pulse has to start 
        # self._0_pulse_stop = PCA count (0-4095) when the pulse has to stop for "off" position of the servo
        # se1_pulse_stop = PCA count (0-4095) when the pulse has to stop for "on" position of the servo
        # It is valid if stop is smaller than start (i.e. the pulse times operate
        # modulo 4096)

        # Stagger the start of the pulses, perhaps it
        # makes that the total current be a bit lower 
        # Not significant if period_us is small
        # Pulse starts at the same time for "on" and "off" position of the servo
        self._pulse_start = round(self._pin/16*4096)
        # Calculate pulse end for OFF position and store into self._0_pulse_stop
        length0 = round(pulse0_us/self._period_us*4096)
        self._0_pulse_stop = (self._pulse_start + length0) % 4096
        
        # Calculate pulse end for ON position and store into into self._1_pulse_stop
        length1 = round(pulse1_us/self._period_us*4096)
        self._1_pulse_stop = (self._pulse_start + length1) % 4096

    def stop_pwm( self ):
        # Stop PWM signal to lower power consumption and heat
        # start=0, stop=0 stops PWM pulse train.
        # For some servos this may reduce current to < 1mA.
        # Some servos like the MG92B servos don't need this
        self._driver.set_pwm( self._pin, 0, 0 )