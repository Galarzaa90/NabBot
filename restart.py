import asyncio
import os
asyncio.sleep(5)
if(platform.system == "Linux"):
    os.system("python nabnot.py")
else:
    os.system("python3 nabbot.py")