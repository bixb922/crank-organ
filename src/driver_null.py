# Copyright (c) 2023-2025 Hermann von Borries
# MIT license

# Null driver, used as default if the real driver
# has errors (i.e MCP23017 not found, disconnected) 
# to avoid a nasty crash of the software and enable to
# continue working.

from driver_base import BasePin, BaseDriver

NULL_PIN_SERIAL = 0

class NullDriver(BaseDriver):

    # __init__ is done by base class
    def define_pin( self, *args ):
        return NullPin(self, *args)

class NullPin(BasePin):
    def __init__( self, *args ):
        global NULL_PIN_SERIAL
        super().__init__( *args )
        self._pin = NULL_PIN_SERIAL
        NULL_PIN_SERIAL += 1


    def on( self ):
        pass
    
    def off( self ):
        pass
    
    