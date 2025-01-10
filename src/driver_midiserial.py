# Copyright (c) 2023 Hermann von Borries
# MIT license

# Controller for MIDI output over serial
from machine import UART

from driver_base import BasePin, BaseDriver

class MIDISerialDriver(BaseDriver):
    def __init__( self, uart, pin, channel ):
        # Default rx is 9 for UART 0
        assert 1 <= uart <= 2
        assert 0 <= channel <= 15
        self._uart = UART( uart, baudrate=31250, tx=pin )
        # Have bytearray with the command ready, format is:
        # event+channel, note, velocity
        self._note_on = bytearray( (0x90 + channel, 0, 127))
        self._note_off = bytearray((0x80 + channel, 0,   0))
        # Could store channel number here to send all_notes_off
        # only on the defined channel.
        super().__init__()
 
    def _note_message( self, midi_number, note_on ):
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
            self._uart.write( bytearray( (0xB0+channel, 123, 0) ) )

    def define_pin( self, *args):
        return VirtualMIDIPin( self, *args )
   
class VirtualMIDIPin(BasePin):
    # >>> some pin number must be supplied in pinout.json
    # >>> for example 0, 1, 2, ...
    #def __init__( self, driver, pin_number, rank, nominal_midi_note ):
    #    super().__init__(driver, pin_number, rank, nominal_midi_note )
        # Use the MIDI note number as pin number to
        # get a unique identifier with __repr__
        # This is also assigned this way in pinout.html
        # but it's better to reinforce here.
    #    self._pin = self.nominal_midi_number

    def value( self, val ):
        self._driver._note_message( self.nominal_midi_number, val )
