import asyncio
import os
import platform

print("Restarting in 5 seconds...")
asyncio.sleep(5)
print("Restarting...")

if(platform.system() == "Linux"):
    os.system("python3 nabbot.py") 
else:
    os.system("python nabbot.py")

