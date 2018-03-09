import time
import os
import sys

print("Restarting in 3 seconds...")
time.sleep(3)
print("Restarting...")
if len(sys.argv) > 1:
    resetid = sys.argv[1]
else:
    resetid = 0
try:
    os.system("python nabbot.py {0}".format(resetid))
except KeyboardInterrupt:
    pass

