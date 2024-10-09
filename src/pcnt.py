from machine import mem32, Pin
import sys
import asyncio
from micropython import const

# Comments refer to the ESP32 Technical Manual
# or ESP32-S3 technical manual. Comments with C language
# are taken from ESP-IDF source.

def set_bit_field( reg, bitpos, length, value ):
    assert 0 <= bitpos <= (32-length)
    mask = (1<<length)-1
    assert 0 <= value <= mask  
    # Read value and clear field
    r = mem32[reg] & ~(mask << bitpos)
    mem32[reg] = r | (value << bitpos)

def get_gpio_number( pin ):
    # Get the pin number of MicroPython Pin object
    if not isinstance( pin, Pin ):
        raise ValueError
    s = str(pin)
    assert s[0:4] == "Pin("
    return int( s[4:-1])

def singleton(cls):
    instance = None
    def getinstance(*args, **kwargs):
        nonlocal instance
        if instance is None:
            instance = cls(*args, **kwargs)
        return instance
    return getinstance


class BaseRegisters:
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
        # ESP32: Register 17.4. PCNT_Un_CNT_REG (n: 0­7) (0x28+0x0C*n)
        # Bits 16-31 are 0 (reserved)
        return self.PCNT_CNT_base + 4*unit
    
    def PCNT_Un_STATUS_REG( self, unit ):
        return self.PCNT_Un_STATUS_REG_base + 4*unit
    
    def GPIO_FUNCy_IN_SEL_CFG_REG( self, unit, channel, input_number ):
        # Return address of input selection configuration register
        # for counter, channel and signal/control indicated
        # input_number: 0=signal,1=control

        assert 0 <= unit < self.PCNT_units
        assert 0 <= channel <= 1
        assert 0 <= input_number <= 1

        peripheral = self.get_peripheral( unit, channel, input_number )
    
        # ESP32-S3: Register 6.19. GPIO_FUNCy_IN_SEL_CFG_REG (y: 0-255) (0x0154+0x4*y)
        # ESP32: Register 4.31. GPIO_FUNCy_IN_SEL_CFG_REG (y: 0-255) (0x130+0x4*y)
        return self.GPIO_FUNCy_IN_SEL_CFG_base + 0x4*peripheral


# class ESP32reg(BaseRegisters):
#     PCNT_units = 8

#     # Register address where PCNT registers start
#     PCNT_base = 0x3FF5_7000
#     # Interrupt clear register
#     # Register 17.8. PCNT_INT_CLR_REG (0x008c)
#     PCNT_INT_CLR_REG = PCNT_base + 0x008c
#     # Interrupt enable register
#     # Register 17.7. PCNT_INT_ENA_REG (0x0088)
#     PCNT_INT_ENA_REG = PCNT_base + 0x0088
#     # Raw interrupts
#     #
#     PCNT_INT_RAW_REG = PCNT_base + 0x0080
    
#     # Status register
#     # Register 17.10. PCNT_Un_STATUS_REG (n: 0­7) (0x90+0x0C*n)
#     PCNT_Un_STATUS_REG_base = PCNT_base + 0x0090
#     # Control register
#     # Register 17.9. PCNT_CTRL_REG (0x00b0)
#     PCNT_CTRL_REG =  PCNT_base + 0x00b0

#     # Base register for configuration
#     # Register 17.1. PCNT_Un_CONF0_REG (n: 0-7) (0x0+0x0C*n)
#     # Register 17.2. PCNT_Un_CONF1_REG (n: 0-7) (0x4+0x0C*n)
#     # Register 17.3. PCNT_Un_CONF2_REG (n: 0-7) (0x8+0x0C*n)
#     PCNT_CONF_base = PCNT_base
    
#     # Base registers for counters
#     # Register 17.4. PCNT_Un_CNT_REG (n: 0-7) (0x28+0x0C*n)
#     # 17.3 Register Summary: 0x3FF57060
#     # There seems to be a inconsistency in the docs here?
#     # ESP-IDF code in pcnt_reg.h shows 
#     # define PCNT_U0_CNT_REG          (DR_REG_PCNT_base + 0x0060)
#     # so 0x3FF5_7060 seems to be correct.
#     # for ESP32. 
#     PCNT_CNT_base =  PCNT_base

#     # Register 5.19. DPORT_PERIP_CLK_EN_REG (0x0C0)
#     DPORT_PERIP_CLK_EN_REG = 0x3FF000C0
#     # Register 5.20. DPORT_PERIP_RST_EN_REG (0x0C4)
#     DPORT_PERIP_RST_EN_REG = 0x3FF000C4
#     # On ESP32-S3, the name is SYSTEM_ instead of DPORT_
#     # Let's adopt ESP32-S3 names here
#     # The bit to enable/reset the PCNT is the same on both
#     # architectures 
#     SYSTEM_PERIP_CLK_EN0_REG = DPORT_PERIP_CLK_EN_REG
#     SYSTEM_PERIP_RST_EN0_REG = DPORT_PERIP_RST_EN_REG 

#     # Table 1-6 Peripheral Address Mapping in Chapter 1 System and Memory.
#     GPIO_base = 0x3FF4_4000
#     # Register 4.31. GPIO_FUNCy_IN_SEL_CFG_REG (y: 0-255) (0x130+0x4*y)
#     GPIO_FUNCy_IN_SEL_CFG_base = GPIO_base + 0x130
#     # For ESP32 this is the value of the GPIO number
#     # that supplies "constantly low"
#     # to the GPIO Matrix
#     GPIO_FUNCy_IN_SEL_low = 0x30
    
#     def get_peripheral( self, unit, channel, input_number ):
#         # Get peripheral signal number of the PCNT device,
#         # unit, signal and channel to be used for the GPIO Matrix
#         # according to
#         # Table 6-2. Peripheral Signals via GPIO Matrix
#         assert 0 <= unit < self.PCNT_units
#         assert 0 <= channel <= 1
#         assert 0 <= input_number <= 1
        
#         # On the ESP32 functions 39 to 58 and
#         # 71 to 92 are for PCNT (two different ranges)
#         # Table 4-2. GPIO Matrix Peripheral Signals
#         if unit <= 4:
#             # For units 0 to 4
#             peripheral =  39 + unit*4 + input_number*2 + channel
#         else:
#             # For units 5 to 7
#             peripheral = 71 + (unit-4)*4 + input_number*2 + channel
#         assert 39 <= peripheral <= 58 or 71 <= peripheral <= 82
#         return peripheral
        
class ESP32S3reg(BaseRegisters):
    PCNT_units = 4

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
    
    # Base for counters
    # Register 38.5. PCNT_Un_CNT_REG (n: 0-3) (0x0030+0x4*n)
    PCNT_CNT_base =  PCNT_base + 0x0030

    # Register 38.6. PCNT_Un_STATUS_REG (n: 0-3) (0x0050+0x4*n)
    PCNT_Un_STATUS_REG_base = PCNT_base + 0x0050
    
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
    
    def get_peripheral( self, unit, channel, input_number ):
        assert 0 <= unit <= MC.PCNT_units
        assert 0 <= channel <= 1
        assert 0 <= input_number <= 1
        # Get peripheral signal number of the PCNT device,
        # unit, signal and channel for the GPIO Matrix
        # according to
        # Table 6-2. Peripheral Signals via GPIO Matrix 
        peripheral =  33 + unit*4 + input_number*2 + channel
        assert 33 <= peripheral <= 48
        return peripheral

    
MC = None
@singleton
class _PCNThardware:
    def __init__( self ):
        global MC
        MC = MC or ESP32S3reg()
        self.pcnt_instances = {}
        self._initialize_all()
        
    def register( self, cls, unit ):
        if not( 0<= unit < MC.PCNT_units):
            raise ValueError

        pcnt = self.pcnt_instances.get(unit)
        if not pcnt:
            pcnt = object.__new__(cls)
            self.pcnt_instances[unit] = pcnt
        return pcnt
    
    def _initialize_all( self ):
        # Initialize complete PCNT, all units
        # Get PCNT out of reset state
        # and enable clock for PCNT in SYSTEM/DPORT register
        # If clock not set, the registers cannot be written
        # and show 0 if attempting to write something there.s
        SYSTEM_PCNT_CLK_EN = 1<<10
        SYSTEM_PCNT_RST = 1<<10
        # For ESP32, the bits have other names:
        # DPORT_PCNT_RST = 1 << 10
        # DPORT_PCNT_CLK_EN = 1 << 10
        # On ESP32 the registers are called DPORT_... instead
        # of SYSTEM_... as they are called on ESP32-S3
        # But the bit for the PCNT is in the same position.

        # See issue #12592 MicroPython GITHUB for this code.
        # Set this bit to enable PCNT clock. (R/W)
        mem32[MC.SYSTEM_PERIP_CLK_EN0_REG] |= SYSTEM_PCNT_CLK_EN

        # SYSTEM_PCNT_RST Set this bit to reset PCNT. (R/W)
        # i.e.: Clear this bit to enable PCNT and get it out
        # of "reset" state.
        mem32[MC.SYSTEM_PERIP_RST_EN0_REG] &= ~SYSTEM_PCNT_RST

        # Clear all interrupts, no interrupt handling here
        # for all units. Clear pending interrupts if any.
        mem32[MC.PCNT_INT_ENA_REG] = 0
        mem32[MC.PCNT_INT_CLR_REG] = 0xf

        # And reset all PCNT units
        for unit in range(MC.PCNT_units):
            self.initialize_pcnt_unit( unit )

    def initialize_pcnt_unit( self, unit ):
        # Reset a PCNT unit:
        #    pause counter
        #    reset counter to zero
        #    reset all configuration registers leaving
        #    no thresholds enabled, no counting signals.
        #    disable all interrupts
        #    Only glitch filter enabled with hardware default value.
        #    Reset the the register of the GPIO Matrix 
        #    corresponding to this unit

        # Stop count: ESP-IDF pcnt_ll_stop_count(group->hal.dev, unit_id);
        PCNT_CNT_PAUSE_Un = 1 << (2 * unit + 1)
        mem32[MC.PCNT_CTRL_REG] |= PCNT_CNT_PAUSE_Un
        # Clear count: ESP-IDF pcnt_ll_clear_count(group->hal.dev, unit_id);
        # Set count to zero by
        # Set and then clear "reset to zero" bit 
        PCNT_PULSE_CNT_RST_Un = (1 << (2 * unit))
        mem32[MC.PCNT_CTRL_REG] |= PCNT_PULSE_CNT_RST_Un
        mem32[MC.PCNT_CTRL_REG] &= ~PCNT_PULSE_CNT_RST_Un

        # Get the three configuration registgers
        reg0 = MC.PCNT_Un_CONF_REGx( unit, 0 )
        reg1 = MC.PCNT_Un_CONF_REGx( unit, 1 )
        reg2 = MC.PCNT_Un_CONF_REGx( unit, 2 )
        # Leave only filter enabled with threshold 16
        # which is the default. Configure all other bits to 0
        # This means: no threshold detection, no limits, no interrups
        mem32[reg0] = (1 << 10) | 0x10
        mem32[reg1] = 0
        mem32[reg2] = 0

        # Disconnect GPIOs that could be still connected to the PCNT
        # for this unit
        for channel in range(2):
            for signal in range(2):
                gpio_matrix_reg = MC.GPIO_FUNCy_IN_SEL_CFG_REG( unit, channel, signal )
                # set GPIO_SIGy_IN_SEL to 0
                # set GPIO_FUNCy_IN_INV_SEL to 0
                # set GPIO number to "constantly low input"
                mem32[gpio_matrix_reg] = MC.GPIO_FUNCy_IN_SEL_low


class PCNT:
    # Rising/falling values
    IGNORE = const(0) 
    INCREMENT = const(1)
    DECREMENT = const(2)
    
    # Mode_low/mode_high values
    HOLD = const(0)
    REVERSE = const(1)
    
    # IRQ types (these are in the same order as the bits in the 
    # status register for simplicity)
    IRQ_ZERO = 64
    IRQ_MAX = 32
    IRQ_MIN = 16
    IRQ_THRES0 = 8
    IRQ_THRES1 = 4
    
    def __new__(cls, unit, *_args, **_kwargs):
        return _PCNThardware().register( cls, unit )
    
    def __init__( self, unit, *args, **kwargs):
        self.unit = unit

        # Reset this unit of the PCNT to known state
        _PCNThardware().initialize_pcnt_unit( unit )

        # Precompute counter register address for a 
        # fast read of the counter in self.count()
        self.counter_reg = MC.PCNT_Un_CNT_REG( self.unit )
        
        # irq_flags are the only proper state of this class
        self.irq_flags = 0
        self.init( *args, **kwargs )
        
    def init( self, *args, **kwargs ):
        
        self._config( *args, **kwargs )
        # Needs configuration and counter.start()

    def _config( self, channel=None, pin=None, rising=None, falling=None, mode_pin=None, mode_low=None, mode_high=None, filter=None,  min=None, max=None, threshold0=None, threshold1=None, value=None ):

        for input_number, pin_object in enumerate([pin, mode_pin]): 
            if pin_object:
                if channel is None or not( 0 <= channel <= 1):
                    raise ValueError
                gpio_number = get_gpio_number( pin_object )
                self._connect_gpio_with_pcnt( gpio_number, channel, input_number )
        
        # ESP32-S3 Register 38.1. PCNT_Un_CONF0_REG (n: 0-3) (0x0000+0xC*n)
        # ESP32 Register 17.1. PCNT_Un_CONF0_REG (n: 0-7) (0x0+0x0C*n)
        reg0 = MC.PCNT_Un_CONF_REGx( self.unit, 0 )
        reg1 = MC.PCNT_Un_CONF_REGx( self.unit, 1 )
        reg2 = MC.PCNT_Un_CONF_REGx( self.unit, 2 )

        # reg2: L_LIM, H_LIM. L_LIM bit 13, H_LIM bit 12
        # reg1: THRES1, THRES0. Thres1 bit 15, Thres0 bit 14
        for limit_val, minimum, maximum, limitpos, register in (
             ( max,            0, 2**15-1,  0, reg2),
             ( min,       -2**15,       0, 16, reg2),
             (threshold0, -2**16, 2**16-1,  0, reg1),
             (threshold1, -2**16, 2**16-1, 16, reg1),
        ):
            if limit_val is not None:
                if not( minimum <= limit_val <= maximum):
                    raise ValueError
                # Set the value of the limit
                set_bit_field( register, limitpos, 16, limit_val&0xffff )
                self.zero()
                #print(f"config CNT {mem32[self.counter_reg]=}")

        # Bit positions of modes in config register 0
        # ch0 neg_mode 16-17
        # ch0 pos_mode 18-19
        # ch1 neg_mode 24-25
        # ch1 pos_mode 26-27
        # ch0 hctrl_mode 20-21
        # ch0 lctrl_mode 22-23
        # ch1 hctrl-mode 28-29
        # ch1 lctrl_mode 30-31
        if channel is None:
            # >>>the right thing to do?
            # >>> should perhaps factor channel out?
            channel = 0
        for vconfig, bitpos, length, maxval, channel8 in ( 
                (falling, 16, 2, 2, True), 
                (rising, 18, 2, 2, True), 
                (mode_high, 20, 2, 2, True), 
                (mode_low,  22, 2, 2, True), 
                (filter, 0, 10, 1023, False),
                (1 if filter else 0, 10, 1, 1, False)
        ):
            if vconfig is not None:
                if not( 0 <= vconfig <= 2**length-1):
                    raise ValueError
                if channel8:
                    # bit position depends on channel
                    if channel is None:
                        raise ValueError
                    bitpos += channel * 8
                set_bit_field( reg0, bitpos, length, vconfig )

        #>>>>better code for filter.
        #if filter is not None:
        #    set_bit_field( reg0, 10, 1023, filter )
        #    set_bit_field( reg0, 10, 1, bool(filter) )


        if value is not None:
            if value == 0:
                self.zero()
            else:
                raise ValueError

    def _connect_gpio_with_pcnt( self, gpio_number, channel, input_number ):
        # Connect the gpio via the GPIO Matrix to
        # the PCNT self.unit/channel/signal.
        # input_number=0 means "signal input", signal=1 means "control input" input of the PCNT
        if not( 0 <= channel <= 1):
            raise ValueError
        if not( 0 <= input_number <= 1 ):
            raise ValueError
            
        # Get register according to peripheral function number
        # See table in GPIO Matrix chapter.
        gpio_matrix_reg = MC.GPIO_FUNCy_IN_SEL_CFG_REG( self.unit, channel, input_number )
        # Set GPIO_SIG_IN_SEL to activate GPIO Matrix
        # for this connection as "input signal" and connect
        # gpio_number to the specified input of the PCNT unit
        GPIO_SIG_IN_SEL = 1<<7
        mem32[gpio_matrix_reg] = GPIO_SIG_IN_SEL + gpio_number

    def deinit( self ):
        _PCNThardware().initialize_pcnt_unit( self.unit )

    def start( self ):
        # Start counting
        PCNT_CNT_PAUSE_Un = (1 << (2 * self.unit + 1))
        mem32[MC.PCNT_CTRL_REG] &= ~PCNT_CNT_PAUSE_Un

    def pause( self ):
        # Stop counting, resume with start()
        PCNT_CNT_PAUSE_Un = (1 << (2 * self.unit + 1))
        mem32[MC.PCNT_CTRL_REG] |= PCNT_CNT_PAUSE_Un

    def zero( self ):
        # Set counter to zero
        PCNT_PULSE_CNT_RST_Un = (1 << (2 * self.unit))
        mem32[MC.PCNT_CTRL_REG] |= PCNT_PULSE_CNT_RST_Un
        mem32[MC.PCNT_CTRL_REG] &= ~PCNT_PULSE_CNT_RST_Un

    # value() must be called before the counter overflows,
    # i.e. at least every 32768 counts. This will limit the maximum
    # frequency that can be handled.
    # For example, if value() can be called every 1 second,
    # the maximum frequency that can be measured is about 32kHz.
    # If it can be called 10 times a second, the max frequency
    # is about 300kHz.
    @micropython.viper # type:ignore
    def value( self )->int:
        self._check_irq()
        c = ptr32(self.counter_reg)[0] # type:ignore
        # Convert from signed 16 bit integer to Python int
        if c >= 32768:
            c -= 65536
        return c

    @micropython.viper # type:ignore
    def raw_value( self )->int:
        self._check_irq()
        return ptr32(self.counter_reg)[0] # type:ignore

    
    def irq( self, callback=None, trigger=None ):
        # Establish a "pseudo irq" handler, i.e. a callback when
        # the counter exceeds one of the limits
        if callback:
            # Register callback
            self.callback = callback
        if trigger:
            reg0 = MC.PCNT_Un_CONF_REGx( self.unit, 0 )
            for trigbit, bitpos in (
                    (PCNT.IRQ_THRES1,15),
                    (PCNT.IRQ_THRES0,14),
                    (PCNT.IRQ_MIN,13),
                    (PCNT.IRQ_MAX,12),
                    (PCNT.IRQ_ZERO,11)):
                if trigbit & trigger:
                    set_bit_field( reg0, bitpos, 1, 1 )

        # return so that
        # pcnt.irq().flags() is the bit mask of IRQs detected
        return self
    
    def flags( self ):
        # method to return pcnt.irq().flags()
        f = self.irq_flags
        self.irq_flags = 0
        return f

    @micropython.viper # type:ignore
    def _check_irq( self ):
        # Quick check for the 99.9% of the times this is called
        if ptr32(uint(MC.PCNT_INT_RAW_REG))[0] == 0: # type:ignore
            return
        unit = int(self.unit)
        # Was interrupt raised? That means the hardware counter
        # reached H_LIM, L_LIM, threshold or zero
        if ptr32(uint(MC.PCNT_INT_RAW_REG))[0] & (1<<unit): # type:ignore
            # self.trigger bits are defined to be equal to the
            # status register bits here
            self.irq_flags = ptr32(MC.PCNT_Un_STATUS_REG( unit ))[0] # type:ignore
            # Clear interrupt
            bit = 1<<unit
            ptr32(MC.PCNT_INT_CLR_REG)[0] |= bit # type:ignore
            # And exit "cleared" state again
            ptr32(MC.PCNT_INT_CLR_REG)[0] &= int(bit ^ -1) # type:ignore
            
            # Call "pseudo interrupt" handler
            self.callback( self )

    


            