"""Refresh official schedules without manufacturing missing collection dates."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import date, timedelta

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import ApiError, ToulouseApi
from .const import DOMAIN
from .green import GreenClient, GreenError
from .schedule import parse_rule

LOGGER = logging.getLogger(__name__)


class ToulouseCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass, entry):
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(hours=12),
        )
        self.entry = entry
        self.api = ToulouseApi(async_get_clientsession(hass))
        self.green = GreenClient(async_get_clientsession(hass))

    async def _async_update_data(self):
        streams = deepcopy(
            self.entry.options.get("streams", self.entry.data["streams"])
        )
        address = self.entry.data["address"]
        for stream, config in streams.items():
            if stream == "green" and config.get("green_plan"):
                try:
                    schedule = await self.green.async_schedule(
                        address["latitude"], address["longitude"]
                    )
                    if schedule is None:
                        raise GreenError(
                            "Adresse hors des secteurs publiés de collecte végétale"
                        )
                    plan = config["green_plan"]
                    year = dt_util.now().year
                    dates = schedule.dates(plan, date(year, 1, 1), date(year + 2, 1, 1))
                    config.update(
                        mode="manual",
                        dates=",".join(d.isoformat() for d in dates),
                        valid_until=schedule.valid_until(plan).isoformat(),
                        description=schedule.raw,
                        error=None,
                    )
                except GreenError as err:
                    config.update(mode="unavailable", error=str(err))
                continue
            if not config.get("route_key") or config["mode"] != "recurring":
                continue
            try:
                routes = await self.api.routes(
                    stream, address["latitude"], address["longitude"]
                )
                route = next(
                    (r for r in routes if r["key"] == config["route_key"]), None
                )
                if route is None:
                    raise ApiError("Tronçon introuvable : reconfigurer l’adresse")
                parse_rule(route["rule"])
                config.update(rule=route["rule"], description=route["rule"], error=None)
            except (ApiError, ValueError) as err:
                # Keep other streams working; do not expose an unverified stale date.
                config.update(mode="unavailable", error=str(err))
        return streams
