import time
import os
import platform
import sys

print("Restarting in 3 seconds...")
time.sleep(3)
print("Restarting...")
if len(sys.argv) > 1:
    resetid = sys.argv[1]
else:
    resetid = 0
    
if(platform.system() == "Linux"):
    os.system("python3 nabbot.py {0}".format(resetid)) 
else:
    os.system("python nabbot.py {0}".format(resetid))

