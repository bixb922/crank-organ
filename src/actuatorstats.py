
class ActuatorStats:
    # Holds actuator statistics. This is a separate very lightweight class
    # to avoid the dependency of low level drivers (driver_*.py)
    # from drehorgel.py
    #
    @classmethod
    def zero(cls):
        cls.stats = {}

    @classmethod
    def max( cls, key, value ):
        cls.stats.setdefault( key, 0 )
        cls.stats[key] = max( cls.stats[key], value )
    
    @classmethod
    def count( cls, key ):
        cls.stats.setdefault( key, 0 )
        cls.stats[key] += 1

    @classmethod 
    def get( cls ):
        # get statistics
        return cls.stats

    
ActuatorStats.zero()