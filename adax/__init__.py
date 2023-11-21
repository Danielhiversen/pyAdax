"""Support for Adax wifi-enabled home heaters."""
import asyncio
import datetime
import json
import logging

import async_timeout
from aiohttp import ClientError

_LOGGER = logging.getLogger(__name__)

API_URL = "https://api-1.adax.no/client-api"
RATE_LIMIT_SECONDS = 30

class RateLimitError(Exception):
    pass


class Adax:
    """Adax data handler."""

    def __init__(self, account_id, password, websession):
        """Init Adax data handler."""
        self._account_id = account_id
        self._password = password
        self.websession = websession
        self._access_token = None
        self._rooms = []
        self._energy = {}
        self._timeout = 10

        self._prev_request = datetime.datetime.utcnow() - datetime.timedelta(hours=2)
        self._set_event = asyncio.Event()
        self._write_task = None
        self._pending_writes = {"rooms": []}

    async def get_rooms(self):
        """Get Adax rooms."""
        await self.update()
        return self._rooms

    async def update(self):
        """Update data."""
        if (
            datetime.datetime.utcnow() - self._prev_request
            < datetime.timedelta(seconds=RATE_LIMIT_SECONDS)
            or self._write_task is not None
        ):
            _LOGGER.debug("Skip update due to rate limit")
            return
        await self.fetch_rooms_info()

    async def set_room_target_temperature(self, room_id, temperature, heating_enabled):
        """Set target temperature of the room."""
        if self._write_task is not None:
            self._write_task.cancel()
        self._pending_writes["rooms"] = [
            room
            for room in self._pending_writes["rooms"]
            if not room.get("id") == room_id
        ]

        self._pending_writes["rooms"].append(
            {
                "id": room_id,
                "heatingEnabled": heating_enabled,
                "targetTemperature": str(int(temperature * 100)),
            }
        )

        self._write_task = asyncio.ensure_future(
            self._write_set_room_target_temperature(self._pending_writes.copy())
        )
        await self._set_event.wait()

    async def _write_set_room_target_temperature(self, json_data):
        now = datetime.datetime.utcnow()
        delay = max(
            1,
            (
                self._prev_request
                + datetime.timedelta(seconds=RATE_LIMIT_SECONDS)
                - now
            ).total_seconds(),
        )
        _LOGGER.debug("Delaying request %.1fs", delay)
        await asyncio.sleep(delay)

        for k in range(3):
            try:
                resp = await self._request(API_URL + "/rest/v1/control/", json_data=json_data)
            except RateLimitError:
                await asyncio.sleep(10*k)
            else:
                break
        if resp  is not None:
            for room_i in self._rooms.copy():
                for room_j in json_data.get("rooms"):
                    if room_i["id"] == room_j["id"]:
                        room_i["targetTemperature"] = (
                            float(room_j.get("targetTemperature", 0)) / 100.0
                        )
                        if room_j.get("heatingEnabled") is not None:
                            room_i["heatingEnabled"] = room_j["heatingEnabled"]
                        break

        self._pending_writes = {"rooms": []}
        self._set_event.set()
        self._set_event.clear()
        self._write_task = None

    async def fetch_rooms_info(self):
        """Get rooms info."""
        try:
            response = await self._request(API_URL + "/rest/v1/content/?withEnergy=1", retry=1)
        except RateLimitError:
            return
        if response is None:
            return
        json_data = await response.json()
        if json_data is None:
            return

        for room in json_data["rooms"]:
            for dev in json_data["devices"]:
                if dev["roomId"] == room["id"]:
                    room["energyWh"] = room.get("energyWh", 0) + dev["energyWh"]
            room["targetTemperature"] = room.get("targetTemperature", 0) / 100.0
            room["temperature"] = room.get("temperature", 0) / 100.0
        self._rooms = json_data["rooms"]

    async def fetch_energy_info(self):
        """Get rooms info."""
        room_energy = {}
        for room in self._rooms:
            room_id = room["id"]
            try:
                response = await self._request(f"{API_URL}/rest/v1/energy_log/{room_id}", retry=1)
            except RateLimitError:
                return
            if response is None:
                return
            json_data = await response.json()
            if json_data is None:
                return
            room_energy[room_id] = json_data
        self._energy = room_energy


    async def _request(self, url, json_data=None, retry=0):
        if (
            datetime.datetime.utcnow() - self._prev_request
            < datetime.timedelta(seconds=RATE_LIMIT_SECONDS)
        ):
            _LOGGER.warning("Max 1 request per %s seconds", RATE_LIMIT_SECONDS)
            raise RateLimitError("Max 1 request per %s seconds", RATE_LIMIT_SECONDS)

        self._prev_request = datetime.datetime.utcnow()
        _LOGGER.debug("Request %s %s, %s", url, retry, json_data)
        if self._access_token is None:
            self._access_token = await get_adax_token(
                self.websession, self._account_id, self._password
            )
            if self._access_token is None:
                return None

        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            async with async_timeout.timeout(self._timeout):
                if json_data:
                    response = await self.websession.post(
                        url, json=json_data, headers=headers
                    )
                else:
                    response = await self.websession.get(url, headers=headers)

            if response.status != 200:
                self._access_token = None
                if retry > 0:
                    if response.status == 429:
                        _LOGGER.warning("Too many requests")
                        return None
                    return await self._request(url, json_data, retry=retry - 1)
                _LOGGER.error(
                    "Error connecting to Adax, response: %s %s",
                    response.status,
                    response.reason,
                )
                return None
        except ClientError as err:
            self._access_token = None
            if retry > 0 and "429" not in str(err):
                return await self._request(url, json_data, retry=retry - 1)
            _LOGGER.error("Error connecting to Adax: %s ", err, exc_info=True)
            raise
        except asyncio.TimeoutError:
            self._access_token = None
            if retry > 0:
                return await self._request(url, json_data, retry=retry - 1)
            _LOGGER.error("Timed out when connecting to Adax")
            raise
        self._prev_request = datetime.datetime.utcnow()
        return response


async def get_adax_token(websession, account_id, password, retry=3, timeout=10):
    """Get token for Adax."""
    try:
        async with async_timeout.timeout(timeout):
            response = await websession.post(
                f"{API_URL}/auth/token",
                headers={
                    "Content-type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={
                    "grant_type": "password",
                    "username": account_id,
                    "password": password,
                },
            )
    except ClientError as err:
        if retry > 0:
            return await get_adax_token(
                websession, account_id, password, retry=retry - 1
            )
        _LOGGER.error("Error getting token Adax: %s ", err, exc_info=True)
        return None
    except asyncio.TimeoutError:
        if retry > 0:
            return await get_adax_token(
                websession, account_id, password, retry=retry - 1
            )
        _LOGGER.error("Timed out when connecting to Adax for token")
        return None
    if response.status != 200:
        _LOGGER.error(
            "Adax: Failed to login to retrieve token: %s %s",
            response.status,
            response.reason,
        )
        return None
    token_data = json.loads(await response.text())
    return token_data.get("access_token")
