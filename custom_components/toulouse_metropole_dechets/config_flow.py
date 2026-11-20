"""Address selection and explicit confirmation of collection routes."""

from __future__ import annotations

from copy import deepcopy

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import ApiError, ToulouseApi
from .const import DOMAIN, GREEN_URL, MODES, MUNICIPALITY_CODES, OFFICIAL_URL, STREAMS
from .green import GreenClient, GreenError
from .schedule import parse_dates, parse_rule


def choices(values: dict[str, str]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=k, label=v) for k, v in values.items()],
            mode="dropdown",
        )
    )


def initial_streams() -> dict:
    return {
        stream: {
            "mode": "drop_off"
            if stream in {"glass", "food", "textile"}
            else ("appointment" if stream == "bulky" else "unavailable"),
            "source_url": GREEN_URL if stream == "green" else OFFICIAL_URL,
            "description": "Vérifier le service disponible pour votre adresse sur le site officiel.",
            "dates": "",
            "excluded_dates": "",
            "extra_dates": "",
            "exclude_public_shutdowns": stream in {"om", "tri"},
        }
        for stream in STREAMS
    }


class ToulouseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.addresses = []
        self.address = {}
        self.streams = initial_streams()
        self.routes = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ToulouseOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            api = ToulouseApi(async_get_clientsession(self.hass))
            try:
                self.addresses = await api.addresses(user_input["address"])
                if self.addresses:
                    return await self.async_step_address()
                errors["base"] = "no_address"
            except ApiError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("address"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_address(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.address = self.addresses[int(user_input["address_choice"])]
            if self.address.get("citycode") not in MUNICIPALITY_CODES:
                return self.async_abort(reason="outside_metropole")
            await self.async_set_unique_id(self.address["id"])
            self._abort_if_unique_id_configured()
            api = ToulouseApi(async_get_clientsession(self.hass))
            try:
                for stream in ("om", "tri"):
                    self.routes[stream] = await api.routes(
                        stream, self.address["latitude"], self.address["longitude"]
                    )
                return await self.async_step_om()
            except ApiError:
                errors["base"] = "cannot_connect"
        return self.async_show_form(
            step_id="address",
            data_schema=vol.Schema(
                {
                    vol.Required("address_choice"): choices(
                        {str(i): a["label"] for i, a in enumerate(self.addresses)}
                    ),
                }
            ),
            errors=errors,
        )

    async def _route_step(self, stream, user_input):
        errors = {}
        if user_input is not None:
            selection = user_input["route"]
            if selection != "skip":
                route = next(r for r in self.routes[stream] if r["key"] == selection)
                try:
                    parse_rule(route["rule"])
                except ValueError:
                    errors["base"] = "ambiguous_route"
                else:
                    self.streams[stream].update(
                        mode="recurring",
                        rule=route["rule"],
                        route_key=route["key"],
                        description=route["rule"],
                        source_url=route["source_url"],
                    )
            if not errors:
                return await (
                    self.async_step_tri() if stream == "om" else self.async_step_green()
                )
        # Collapse identical street/rule choices; keep nearest segment for refreshing.
        options = {}
        seen = set()
        for route in self.routes[stream]:
            pair = (route["street"], route["rule"])
            if pair in seen:
                continue
            seen.add(pair)
            options[route["key"]] = (
                f"{route['street']} — {route['rule']} (à {route['distance']} m)"
            )
        options["skip"] = "Aucune de ces tournées / à renseigner plus tard"
        return self.async_show_form(
            step_id=stream,
            data_schema=vol.Schema(
                {
                    vol.Required("route"): choices(options),
                }
            ),
            errors=errors,
            description_placeholders={"address": self.address["label"]},
        )

    async def async_step_om(self, user_input=None):
        return await self._route_step("om", user_input)

    async def async_step_tri(self, user_input=None):
        return await self._route_step("tri", user_input)

    async def async_step_green(self, user_input=None):
        errors = {}
        if user_input is not None:
            plan = user_input["green_plan"]
            if plan != "none":
                try:
                    schedule = await GreenClient(
                        async_get_clientsession(self.hass)
                    ).async_schedule(
                        self.address["latitude"], self.address["longitude"]
                    )
                    if schedule is None:
                        errors["base"] = "no_green"
                    else:
                        self.streams["green"].update(mode="manual", green_plan=plan)
                except GreenError:
                    errors["base"] = "cannot_connect"
            if not errors:
                return self.async_create_entry(
                    title=self.address["label"],
                    data={
                        "address": self.address,
                        "streams": self.streams,
                    },
                )
        return self.async_show_form(
            step_id="green",
            data_schema=vol.Schema(
                {
                    vol.Required("green_plan", default="none"): choices(
                        {
                            "none": "Non abonné / renseigner mes dates plus tard",
                            "seasonal": "Abonnement saisonnier gratuit",
                            "paid": "Abonnement annuel payant (inclut les collectes saisonnières)",
                        }
                    ),
                }
            ),
            errors=errors,
        )


class ToulouseOptionsFlow(config_entries.OptionsFlowWithReload):
    """Update a stream without discarding the other six streams."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            self.stream = user_input["stream"]
            return await self.async_step_schedule()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("stream"): choices(STREAMS),
                }
            ),
        )

    async def async_step_schedule(self, user_input=None):
        streams = deepcopy(
            self.config_entry.options.get("streams", self.config_entry.data["streams"])
        )
        current = streams[self.stream]
        errors = {}
        if user_input is not None:
            try:
                for field in ("dates", "excluded_dates", "extra_dates"):
                    parse_dates(user_input.get(field, ""))
                official_green = (
                    self.stream == "green"
                    and user_input.get("green_plan", "none") != "none"
                )
                if user_input["mode"] == "recurring" and not official_green:
                    parse_rule(user_input.get("rule", ""))
            except ValueError:
                errors["base"] = "invalid_schedule"
            else:
                if user_input.get("rule", "") != current.get("rule", ""):
                    current.pop("route_key", None)
                current.update(user_input)
                if user_input.get("green_plan") == "none":
                    current.pop("green_plan", None)
                elif current.get("green_plan"):
                    current["mode"] = "manual"
                current.pop("error", None)
                if current["mode"] == "recurring":
                    current["description"] = current["rule"]
                return self.async_create_entry(title="", data={"streams": streams})
        schema = {
            vol.Required("mode", default=current["mode"]): choices(MODES),
            vol.Optional("rule", default=current.get("rule", "")): str,
            vol.Optional("dates", default=current.get("dates", "")): str,
            vol.Optional(
                "excluded_dates", default=current.get("excluded_dates", "")
            ): str,
            vol.Optional("extra_dates", default=current.get("extra_dates", "")): str,
        }
        if self.stream == "green":
            schema[
                vol.Required("green_plan", default=current.get("green_plan", "none"))
            ] = choices(
                {
                    "none": "Désactivé : utiliser les réglages ci-dessus",
                    "seasonal": "Calendrier officiel saisonnier gratuit",
                    "paid": "Calendrier officiel annuel payant",
                }
            )
        return self.async_show_form(
            step_id="schedule",
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={"stream": STREAMS[self.stream]},
        )
