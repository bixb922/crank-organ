# (c) 2023 Hermann Paul von Borries
# MIT License
# A very simple MicroPython-only Pulse Counter (PCNT) driver
# for ESP32-S3, for low frequencies, i.e. < 100 kHz

from machine import mem32, Pin

# Comments refer to the ESP32 Technical Manual
# or ESP32-S3 technical manual. 

def get_gpio_number( pin ):
    # Get the pin number of MicroPython Pin object
    if not isinstance( pin, Pin ):
        raise ValueError
    s = str(pin)
    assert s[0:4] == "Pin("
    return int( s[4:-1])


class ESP32S3reg:
    # Define hardware register addresses. This driver
    # goes directly to these addresses, bypassing
    # MicroPython and ESP-IDF.

    # Base register address for PCNT registers
    PCNT_base = 0x6001_7000
    # Interrupt clear register
    # Register 38.10. PCNT_INT_CLR_REG (0x004C)
    PCNT_INT_CLR_REG = PCNT_base + 0x004C
    # Interrupt enable register
    # Register 38.9. PCNT_INT_ENA_REG (0x0048)
    PCNT_INT_ENA_REG = PCNT_base + 0x0048
    # Register 38.7. PCNT_INT_RAW_REG (0x0040)
    PCNT_INT_RAW_REG = PCNT_base + 0x0040
    
    # Control register
    # Register 38.4. PCNT_CTRL_REG (0x0060)
    PCNT_CTRL_REG = PCNT_base + 0x0060

    # Base for configuration
    # Register 38.1. PCNT_Un_CONF0_REG (n: 0-3) (0x0000+0xC*n)
    # Register 38.2. PCNT_Un_CONF1_REG (n: 0-3) (0x0004+0xC*n)
    # Register 38.3. PCNT_Un_CONF2_REG (n: 0-3) (0x0008+0xC*n)
    PCNT_CONF_base = PCNT_base
    
    # Base register address for counters
    # Register 38.5. PCNT_Un_CNT_REG (n: 0-3) (0x0030+0x4*n)
    PCNT_CNT_base =  PCNT_base + 0x0030
    # ESP32-S3 has 4 PCNT units
    PCNT_units = 4

    SYSTEM_BASE = 0x600C_0000
    # Register 17.4. SYSTEM_PERIP_CLK_EN0_REG (0x0018)
    SYSTEM_PERIP_CLK_EN0_REG = SYSTEM_BASE + 0x0018
    # Register 17.6. SYSTEM_PERIP_RST_EN0_REG (0x0020)
    SYSTEM_PERIP_RST_EN0_REG = SYSTEM_BASE + 0x0020

    GPIO_base = 0x6000_4000
    # Register 4.31. GPIO_FUNCy_IN_SEL_CFG_REG (y: 0-255) (0x130+0x4*y)
    GPIO_FUNCy_IN_SEL_CFG_base = GPIO_base + 0x0154
    # For ESP32 this is the value that supplies "constantly low"
    # to the GPIO Matrix
    GPIO_FUNCy_IN_SEL_low = 0x3c
    
    def get_peripheral( self, unit, signal, channel ):
        # Get peripheral number of the PCNT device# in the
        #  GPIO Matrix according to
        # Table 6-2. Peripheral Signals via GPIO Matrix 
        peripheral =  33 + unit*4 + signal*2 + channel
        assert 33 <= peripheral <= 48
        return peripheral
    
    def PCNT_Un_CONF_REGx( self, unit, register ):
        # Configuration registers, there are 3 per unit
        # ESP32-S3: Register 38.1. PCNT_Un_CONF0_REG (n: 0-3) (0x0000+0xC*n)
        assert 0 <= register <= 2
        assert 0 <= unit < self.PCNT_units
        return self.PCNT_CONF_base + 0xC*unit + register*4

    def PCNT_Un_CNT_REG( self, unit ):
        assert 0 <= unit < self.PCNT_units
        # Counter register
        # ESP32-S3: Register 38.5. PCNT_Un_CNT_REG (n: 0-3) (0x0030+0x4*n)
        # Bits 16-31 are 0 (reserved)
        return self.PCNT_CNT_base + 4*unit
    
    def GPIO_FUNCy_IN_SEL_CFG_REG( self, unit, channel, signal ):
        # Computes address of input selection configuration register
        # for counter, channel and signal/control indicated
        # signal: 0=signal,1=control

        assert 0 <= unit < self.PCNT_units
        assert 0 <= channel <= 1
        assert 0 <= signal <= 1

        peripheral = self.get_peripheral( unit, signal, channel )
    
        # ESP32-S3: Register 6.19. GPIO_FUNCy_IN_SEL_CFG_REG (y: 0-255) (0x0154+0x4*y)
        # ESP32: Register 4.31. GPIO_FUNCy_IN_SEL_CFG_REG (y: 0-255) (0x130+0x4*y)
        return self.GPIO_FUNCy_IN_SEL_CFG_base + 0x4*peripheral

    
MC = ESP32S3reg()

def _initialize_pcnt( ):
    # Get PCNT out of reset state
    # and enable clock for PCNT in SYSTEM/DPORT register
    # If clock not set, the registers cannot be written
    # and show 0 if attempting to write something there.
    SYSTEM_PCNT_CLK_EN = 1<<10
    SYSTEM_PCNT_RST = 1<<10
    # Set this bit to enable PCNT clock. (R/W)
    mem32[MC.SYSTEM_PERIP_CLK_EN0_REG] |= SYSTEM_PCNT_CLK_EN

    # "SYSTEM_PCNT_RST Set this bit to reset PCNT. (R/W)"
    # i.e.: Clear this bit to enable PCNT and get it out
    # of "reset" state.
    mem32[MC.SYSTEM_PERIP_RST_EN0_REG] &= ~SYSTEM_PCNT_RST

    # Clear all interrupts, no interrupt handling here,
    # for all units. Clear pending interrupts if any.
    mem32[MC.PCNT_INT_ENA_REG] = 0
    mem32[MC.PCNT_INT_CLR_REG] = 0xf

    # And reset all PCNT units
    for unit in range(MC.PCNT_units):
        _initialize_pcnt_unit( unit )

def _initialize_pcnt_unit( unit ):
    # Reset a PCNT unit:
    #    pause counter
    #    reset counter to zero
    #    reset all configuration registers leaving
    #    no thresholds enabled, no counting signals.
    #    disable all interrupts
    #    Only glitch filter enabled with hardware default value.
    #    Reset the the register of the GPIO Matrix 
    #    corresponding to this PCNT unit

    # Stop count, see ESP-IDF pcnt_ll_stop_count(group->hal.dev, unit_id);
    PCNT_CNT_PAUSE_Un = 1 << (2 * unit + 1)
    mem32[MC.PCNT_CTRL_REG] |= PCNT_CNT_PAUSE_Un
    # Clear count, see ESP-IDF pcnt_ll_clear_count(group->hal.dev, unit_id);
    # Set count to zero by
    # Set and then clear "reset to zero" bit 
    PCNT_PULSE_CNT_RST_Un = (1 << (2 * unit))
    mem32[MC.PCNT_CTRL_REG] |= PCNT_PULSE_CNT_RST_Un
    mem32[MC.PCNT_CTRL_REG] &= ~PCNT_PULSE_CNT_RST_Un

    # Get the three configuration registgers
    reg0 = MC.PCNT_Un_CONF_REGx( unit, 0 )
    # Leave only filter enabled with threshold 16
    # which is the default. Configure all other bits to 0
    # This means: no threshold detection, no limits, no interrups
    mem32[reg0] = (1 << 10) | 0x10
    # Set config register 1 and 2 (limits, thresholds) to 0
    mem32[reg0+4] = 0
    mem32[reg0+8] = 0

    # Disconnect GPIOs that are still connected to the PCNT
    # for this unit
    for channel in range(2):
        for signal in range(2):
            gpio_matrix_reg = MC.GPIO_FUNCy_IN_SEL_CFG_REG( unit, channel, signal )
            # set GPIO_SIGy_IN_SEL to 0
            # set GPIO_FUNCy_IN_INV_SEL to 0
            # set GPIO number to "constantly low input"
            mem32[gpio_matrix_reg] = MC.GPIO_FUNCy_IN_SEL_low

# On the first import, reset complete PCNT, 
# since the  MicroPython reset 
# does not know about the PCNT and thus cannot reset it.
_initialize_pcnt()


class PCNT:
    def __init__( self, unit, pin ):
        if not( 0<= unit <= MC.PCNT_units):
            raise ValueError
            
        self.unit = unit
    
        # Reset this unit of the PCNT to known state
        _initialize_pcnt_unit( self.unit )
        self._config_both_edges_up( pin )
        # Precompute counter register address for a 
        # fast read of the counter in self.count()
        self.counter_reg = MC.PCNT_Un_CNT_REG( self.unit )
        

    def _connect_gpio_with_pcnt( self, gpio_number, channel, signal ):
        # Connect the gpio via the GPIO Matrix to
        # the PCNT self.unit/channel/signal.
        # signal=0 means "signal input", signal=1 means "control input" input of the PCNT
        # channel 0 to 1, signal 0=signal input, 1=control inpjut
        # gpio_number: integer with GPIO port number to count            
        # Get register according to peripheral function number
        # See table in GPIO Matrix chapter.
        gpio_matrix_reg = MC.GPIO_FUNCy_IN_SEL_CFG_REG( self.unit, channel, signal )
        # Set GPIO_SIG_IN_SEL to activate GPIO Matrix
        # for this connection as "input signal" and connect
        # gpio_number to the specified input of the PCNT unit
        GPIO_SIG_IN_SEL = 1<<7
        mem32[gpio_matrix_reg] = GPIO_SIG_IN_SEL + gpio_number

    def _config_both_edges_up( self, pin ):
        # Define counter on self.unit, signal input of
        # channel 0 to count upwards on both edges
        # with maximum possible threshold
        gpio_number = get_gpio_number( pin )
        # Connect GPIO to PCNT unit self.unit, channel 0
        # signal input.
        self._connect_gpio_with_pcnt( gpio_number, 0, 0 )

        # Get configuration register 0
        reg0 = MC.PCNT_Un_CONF_REGx( self.unit, 0 )
        # Pos mode (bit 18), increment (value 1)
        # Neg mode (bit 16), increment (value 1)
        # i.e. counts on both edges, that's higher
        # resolution.
        # Maximum threshold of 1023 (bit 0-9), enabled (bit 10)
        # See ESP32-S3 Technical Manual, PCNT_Un_CONF_REG0
        mem32[reg0] = 0x000487ff
        # Start counting by setting "counter reset" bit
        # to zero.
        PCNT_CNT_PAUSE_Un = (1 << (2 * self.unit + 1))
        mem32[MC.PCNT_CTRL_REG] &= ~PCNT_CNT_PAUSE_Un

    def count( self )->int:
        # Besides __init__, this is the only public
        # interface of PCNT.
        # Viper: 5 microseconds at 240 MHz, without viper: 9.4 usec
        # return ptr32(int(self.counter_reg))[0]
        return mem32[self.counter_reg]
    
