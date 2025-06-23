# Writes compiledate.py
from datetime import datetime
dt = datetime.now()
with open("crank-organ/src/compiledate.py", "w") as file:
    file.write(f"compiledate='{dt.year}-{dt.month:02d}-{dt.day:02d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}'\n")
