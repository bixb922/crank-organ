import time
import sys
    
_MAX_TIME = const(3153600000) # 100*365*24*3600 = 100 years, largest time
_SECONDS_PER_DAY = const(86400)
_MIN_YEAR = const(2010)
        
class TTZMonthRule:
    '''
    Month rule parameters are similar to the POSIX STRING TZ FORMAT.
        name: short name, such as "CST", "EET", "MEZ", "+03"
        utc_offset: UTC offset in hours (can be float)
        is_dst: 0=this is not considered DST, 1=this is considered DST
        month: month of year (1-12) when this definition becomes active
        week_of_month: week of month when this rule becomes active.
            1=first week of month
            2=second week of month, etc
            5=indicates the last weeek of month
        day_of_week: day of week when this rule becomes active.
            0=sunday
            1=monday, etc
            6=saturday
        hour: hour of the day, in local time, when the rule takes place.
            0-24 hours, but might be > 24 hours (there are cases).
            This must be the hour when the transition to the new
            rule starts in the PREVIOUS rule's time zone.
    No support for julian day rules.
    No support for fixed UTC offset.
    No support for historical time rules, can be added
    easily externally checking ranges of the timestamp and
    having rules for each time span.
    The current rule is precomputed and cached, so it is fast
    to translate the current timestamp with the now() method,
    '''
    def __init__( self, *args ):
        self.name, utc_offset, self.is_dst, self.month, self.week_of_month, self.day_of_week, hour = args
        # For testing rules:
        # if ( not( 1 <= self.month <= 12 ) or 
             # not( 1 <= self.week_of_month <= 5 ) or
             # not( 0 <= self.is_dst <= 1) or
             # not( 0 <= self.day_of_week <= 6 ) or
             # not( -50 <= hour <= 50 ) or
             # not( -20 <= utc_offset <= 20 ) ):
             # raise ValueError
        self.utc_offset_seconds = utc_offset * 3600
        self.hour_in_seconds = hour * 3600
        
    def compute_transition( self, year ):  
        if year < _MIN_YEAR:
            raise ValueError
            
        # Get UTC epoch seconds at start of month
        start_of_month = time.mktime( (year,self.month,1, 0,0,0, 0,0 ) ) 
            # Even december works in Micropython this way:
        next_month = time.mktime( (year,self.month+1,1, 0,0,0, 0,0 ) ) 
        month_length = int((next_month - start_of_month)/_SECONDS_PER_DAY)
        # Compute the day of week of first of month
        weekday_start_of_month = time.gmtime( start_of_month )[6]+1
        # Adjust for day of week and week of month
        days  = ((7 + self.day_of_week - weekday_start_of_month ) % 7) + (self.week_of_month-1)*7 
        # week_of_month==5 means "last week of the month"
        if self.week_of_month == 5 and days >= month_length:
            days -= 7
        # Get hour of time change (ex: 3am, 11pm) and convert from
        # local time to UTC (rules are in local time)
        seconds =  self.hour_in_seconds - self.utc_offset_seconds
        # Add all this together
        return int(start_of_month + days*_SECONDS_PER_DAY + seconds)

class TinyTZ:
    # utc_offset in hours and fraction
    def __init__( self, rule1, rule2 ):
        '''
        Constructor receives two TinyTZMonth rules. Must be ordereed
        i.e. lower month in the first rule, higher month in the second rule.
        '''
        # For testing:
        # if rule1.month > rule2.month: raise ValueError("rules not ordered")
        self.rules = (rule1,rule2)
        # Mark empty interval - no rule cached
        self.rule_start = _MAX_TIME
        self.rule_end = -1

    def find_rule( self, timestamp ):
        # Search for rule encompassing current timestamp starting one year before now
        year = time.gmtime( timestamp )[0] - 1
        self.rule_start = _MAX_TIME
        while True:
            for rule in self.rules:
                self.rule_end = rule.compute_transition( year )
                self.current_rule = rule
                if self.rule_start <= timestamp < self.rule_end:
                    return
                self.rule_start = self.rule_end
            year += 1

    def now( self ):
        '''
        Returns a time tuple with the current time as local time.
        First 8 elements are the same as Micropython time.localtime():
        year includes the century (for example 2014).
            month is 1-12
            mday is 1-31
            hour is 0-23
            minute is 0-59
            second is 0-59
            weekday is 0-6 for Mon-Sun
            yearday is 1-366
        There are 3 elements added:
            is_dst is 0 or 1
            name is string with the name in the rule
            utc_offset is the utc offset in seconds
        '''
        try:
            t = self.localtime( time.time() )
        except:
            t = list( time.localtime() )
            t.extend( (0,0,0) )
        return t
   
    def localtime( self, timestamp ):
        '''
        Converts timestamp to local time, returns a time tuple with
        11 elements (see now() method.
        Will raise ValueError if year < 2010, this is considered
        as if the clock has not been synchronized.
        '''
        if not( self.rule_start <= timestamp < self.rule_end):
            # Time not in cached rule range, find and cache new time range
            self.find_rule( timestamp )

        # Return type time tuple, adding DST, time zone short name and UTC offset in seconds
        rule = self.current_rule
        return list( time.gmtime( timestamp + rule.utc_offset_seconds ) ) + \
            [ rule.is_dst, rule.name, rule.utc_offset_seconds ]

 

# Define time zone for America/Santiago as of 2023
ttz = TinyTZ(
        TTZMonthRule( "SCL-04", -4, 0, 9,1,6,24),
        TTZMonthRule( "SCL-03", -3, 1, 4,1,6,24)
        )

## Some random ime zone definitions
## UTC
##    name, utc_offset, is_dst, start_month, start_week_of_month, start_day_of_week, start_hour
##    TTZMonthRule( "UTC", 0, 0, 1,1,1,0),
##    TTZMonthRule( "UTC", 0, 0, 6,1,1,0) 
## America/Chicago
##    TTZMonthRule( "CST", -6, 0, 3,2,0,2),
##    TTZMonthRule( "CDT", -5, 1, 11,1,0,2)
## America/Los_Angeles
##    TTZMonthRule( "PST", -8, 0, 3,2,0,2),
##    TTZMonthRule( "PDT", -7, 1, 11,1,0,2) 
## America/New_York
##    TTZMonthRule( "EST", -5, 0, 3,2,0,2 ),
##    TTZMonthRule( "EDT", -4, 1, 11,1,0,2 )
### See https://www.timeanddate.com/time/zone/germany/berlin.    
## Europe/Berlin
##    TTZMonthRule( "CET",  1, 0,  3,5,0,2 ),
##    TTZMonthRule( "CEST",  2, 1, 10,5,0,3 ) 
## Europe/Athens
##    TTZMonthRule( "EET", 2, 0, 3,5,0,3),
##    "rule2": TTZMonthRule( "EEST",3, 1, 10,5,0,4) },
## Asia/Beirut
##    TTZMonthRule( "EET", 2, 0, 3,5,0,0),
##    TZMonthRule( "EEST",3, 1, 10,5,0,0)
### See https://www.timeanddate.com/time/zone/uk/london#:~:text=London%20in%20GMT%20Time%20Zone,DST)%2C%20or%20summer%20time.
##    TTZMonthRule( "GMT",0, 0, 3,5,0,1),
##    TTZMonthRule( "BST",1, 1, 10,5,0,2) 
## Pacific/Auckland
##    TTZMonthRule( "NZST", 12, 0, 9,5,0,2 ),
##    TTZMonthRule( "NZDT", 13, 1, 4,1,0,3 )
##
##Time zones without difference between summer and winter time
##should rewrite the UTC rule with both utc_offset fields set to the UTC
##offset in hours.

