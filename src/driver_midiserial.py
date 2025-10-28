# Copyright (c) 2023-2025 Hermann von Borries
# MIT license

# Controller for MIDI output over serial
from machine import UART

from driver_base import BasePin, BaseDriver

# Not a singleton, there could be different serial
# drivers, each for a uart/pin/channel combination
class MIDISerialDriver(BaseDriver):

    def __init__( self, uart_number, txpin, channel ):
        super().__init__( txpin )

        # "pin" is the GPIO tx pin to use for MIDI output.
        # "uart_number" is the UART number to use, 1 or 2.
        # "channel" is the MIDI channel to use, 0-15.  All
        # notes to this MIDI serial will be sent on the indicated
        # channel. This is because some boards (for example
        # the Organautmatech board) are configured to one channel
        # per board, allowing several boards per MIDI serial output.

        # Default rx is 9 for UART1
        # >>> Should allow user to define rxpin as well!!
        # (to make assignment explicit)
        # (On the pinout.html page the rx pin will show as "used")
        # assert 1 <= uart <= 2
        # assert 0 <= channel <= 15
        self._uart = UART( uart_number, baudrate=31250, tx=txpin )
        # Have bytearray with the MIDI event ready, format is:
        # event+channel, note number, velocity
        self._note_on = bytearray( (0x90 + channel, 0, 127))
        self._note_off = bytearray((0x80 + channel, 0,   0))
        # Could store channel number here to send all_notes_off
        # only on the defined channel.
 
    def _note_message( self, midi_number, note_on ):
        # Since the uart buffer is fairly large (256 bytes) and
        # very unlikely to fill up, uart.write() should never block. 
        # To fill that, more 1000 messages must be sent in 1 second.
        # So there is little need to handle that case.
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
   
class VirtualMIDIPin(BasePin):
    def value( self, val ):
        self._driver._note_message( self.nominal_midi_number, val )

    def __repr__( self ):
        # Must be same definition as solenoid.web_test_pin()
        return  f"{repr(self._driver)}.{self.nominal_midi_number}"

