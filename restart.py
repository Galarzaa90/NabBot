import time
import os
import platform

print("Restarting in 3 seconds...")
time.sleep(3)
print("Restarting...")

if(platform.system() == "Linux"):
    os.system("python3 nabbot.py") 
else:
    os.system("python nabbot.py")

