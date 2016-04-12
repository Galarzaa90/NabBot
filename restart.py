import asyncio
import os
import platform
asyncio.sleep(5)
if(platform.system() == "Linux"):
    os.system("python3 nabbot.py") 
else:
    os.system("python nabbot.py")

