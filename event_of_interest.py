from enum import Enum

class EventOfInterest(Enum):
    FIRST_HEADLINE = 1
    FIRST_OPERATIONAL = 2

# Set the duration over which to look forward and backward at the impact of 
# data center construction on nearby housing estimates.
EVENT_WINDOW_MONTHS = 24

# Set whether to examine the impact of the first headline about data center 
# construction or the opening of the first data center in affected zip codes on home values
EVENT_OF_INTEREST = EventOfInterest.FIRST_OPERATIONAL