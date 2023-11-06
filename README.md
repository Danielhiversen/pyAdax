# pyAdax

Python3 library for Adax heater. 

Control Adax heaters and get measured temperatures.

[Buy me a coffee :)](http://paypal.me/dahoiv)



## Install
```
pip3 install adax
```

## Example:

```python
from adax import Adax
import aiohttp
import asyncio

ACCOUNTID = "<ACCOUNT ID>"  # get your account ID (6 digits) from the Account page in the Adax WiFi app
PASSWORD = "<PASSWORD>" # create a service password under "Remote Api" in the app
withenergy = True

async def main():
    async with aiohttp.ClientSession() as session:
        heater= Adax(ACCOUNTID, PASSWORD, session, withenergy)
        for home in await heater.get_homes():
            print(home)
        for room in await heater.get_rooms():
            print(room)
        for device in await heater.get_devices():
            print(device)
        energy = await heater.get_energy()
        for room_id in energy:
            print(room_id)
            print(energy[room_id])

asyncio.run(main())

```

