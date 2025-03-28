# Copyright (c) 2023 Hermann von Borries
# MIT license

# Controller for MIDI output over serial
from machine import UART

from driver_base import BasePin, BaseDriver

# Not a singleton, there could be different serial
# drivers, each for a uart/pin/channel combination
class MIDISerialDriver(BaseDriver):
    def __init__( self, uart, pin, channel ):
        # Default rx is 9 for UART1
        # >>> Should use default pins or allow user
        # >>> to define rxpin as well.
        # assert 1 <= uart <= 2
        # assert 0 <= channel <= 15
        self._uart = UART( uart, baudrate=31250, tx=pin )
        # Have bytearray with the command ready, format is:
        # event+channel, note number, velocity
        self._note_on = bytearray( (0x90 + channel, 0, 127))
        self._note_off = bytearray((0x80 + channel, 0,   0))
        # Could store channel number here to send all_notes_off
        # only on the defined channel.
        super().__init__()
 
    def _note_message( self, midi_number, note_on ):
        # Since the uart buffer is fairly large (256 bytes) and
        # very unlikely to fill up, uart.write() will not block. 
        # So there is no need to handle that case.
        if note_on:
            self._note_on[1] = midi_number
            self._uart.write( self._note_on )
        else:
            self._note_off[1] = midi_number
            self._uart.write( self._note_off )

   

    def all_notes_off( self ):
        # Control message has three byte message:
        #   Status byte 1011cccc where c is the channel number
        #   0ccccccc controller number
        #   0vvvvvvv controller value
        # Special controller numbers:
        # 120 All Sound Off, immediate silence
        # 121 Reset All Controllers, resets all instrument controllers to default value (including volume)
        # 123 All Notes Off, releases all voices
        # For good measure send all notes off on all channels
        for channel in range(16):
            self._uart.write( bytes( (0xB0+channel, 123, 0) ) )

    def define_pin( self, *args):
        return VirtualMIDIPin( self, *args )
   
    def __repr__( self ):
        # One MIDISerial driver for each UART, there can be more
        # than 1 UART.
        return "MIDISerial." + str(self._uart)[0:6] + ")"
    
class VirtualMIDIPin(BasePin):
    def value( self, val ):
        self._driver._note_message( self.nominal_midi_number, val )
