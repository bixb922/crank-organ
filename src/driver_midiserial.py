# Copyright (c) 2023-2025 Hermann von Borries
# MIT license

# Controller for MIDI output over serial
from machine import UART

from driver_base import SolePin, BaseDriver

# Not a singleton, there could be different serial
# drivers, each for a uart/pin/channel combination
class MIDISerialDriver(BaseDriver):

    def __init__( self, uart_number, txpin, channel, rxpin ):
        super().__init__( txpin )
        # "pin" is the GPIO tx pin to use for MIDI output.
        # "uart_number" is the UART number to use, 1 or 2.
        # "channel" is the MIDI channel to use, 0-15.  All
        # notes to this MIDI serial will be sent on the indicated
        # channel. This is because some boards (for example
        # the Organautmatech board) are configured to respond to one channel
        # per board, allowing several boards per MIDI serial output.

        # assert 1 <= uart <= 2
        # assert 0 <= channel <= 15
        self._uart = UART( uart_number, baudrate=31250, tx=txpin, rx=rxpin )
        # Have bytearray with the MIDI event ready, format is:
        # event+channel, note number, velocity
        self._note_on = bytearray( (0x90 + channel, 0, 127))
        self._note_off = bytearray((0x80 + channel, 0,   0))
 
    def _note_on_message( self, midi_number ):
        # Since the uart buffer is fairly large (256 bytes) and
        # very unlikely to fill up, uart.write() should never block. 
        # To fill that, more 1000 messages must be sent in 1 second.
        # So there is little need to handle that case.
        self._note_on[1] = midi_number
        self._uart.write( self._note_on )

    def _note_off_message( self, midi_number ):
        self._note_off[1] = midi_number
        self._uart.write( self._note_off )

   

    def all_notes_off( self ):
        # Turn all notes off by sending a control message.
        # Control message has three byte message:
        #   Status byte 1011cccc where c is the channel number
        #   0ccccccc controller number
        #   0vvvvvvv controller value
        # Special controller numbers:
        # 120 All Sound Off, immediate silence
        # 121 Reset All Controllers, resets all instrument controllers to default value (including volume)
        # 123 All Notes Off, releases all voices
        # For good measure send all notes off on all channels
        for value in (120,123):
            for channel in range(16):
                self._uart.write( bytes( (0xB0+channel, value, 0) ) )
        # In case the receiver does not understand this message,
        # actuator_bank.all_notes_off() will also force each note off
        # individually.

    def define_pin( self, *args):
        return VirtualMIDIPin( self, *args )
   
# >>> should also send program number?
# >>> currently repr is based on MIDI note number only, if pin
# >>> differ by program number...??? what is the use case?
class VirtualMIDIPin(SolePin):
    # This code supposes the MIDI drives solenoids and not RC Servos
    
    def low_level_on( self ):
        self._driver._note_on_message( self.nominal_midi_number )

    def low_level_off( self ):
        self._driver._note_off_message( self.nominal_midi_number )
        # No tally of battery consumption.

    def __repr__( self ):
        # Must be same definition as solenoid.web_test_pin()
        return  f"{repr(self._driver)}.{self.nominal_midi_number}"

