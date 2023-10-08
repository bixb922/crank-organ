# (c) 2023 Hermann Paul von Borries
# MIT License
print("Go!")

# only main,py and config,json go to the root.
# Software goes to software folder, either previously installed or mounted.

import sys
sys.path.append("/software/mpy")

## extract/update or mount if present
#for frozen in ( "frozen_root", "frozen_software", "frozen_tunelib"):
#	try:
#        # Use import, frozen .py files will free memory if 
#        # extract is used.
#		__import__( frozen )
#	except:
#		pass

import startup
