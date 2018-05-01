import time
import os
import sys

print("Restarting in 3 seconds...")
time.sleep(3)
print("Restarting...")
if len(sys.argv) > 1:
    reset_id = sys.argv[1]
else:
    reset_id = 0
try:
    os.system("python nabbot.py {0}".format(reset_id))
except KeyboardInterrupt:
    pass

