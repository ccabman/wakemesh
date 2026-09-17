"""Configuration flows for WakeMesh."""

from __future__ import annotations

from collections import defaultdict
import logging
from typing import Any

import pyatv
import voluptuous as vol
from pyatv.const import Protocol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_URL
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RouterApiClient, RouterApiError
from .const import (
    CONF_ENTRY_TYPE,
    CONF_IDENTIFIER,
    CONF_SOURCE_ENTITY,
    CONF_TOKEN,
    DEFAULT_URL,
    DOMAIN,
    ENTRY_TYPE_ENGINE,
    ENTRY_TYPE_SPEAKER,
)

LOGGER = logging.getLogger(__name__)
CONF_DESTINATION = "destination"


class WakeMeshConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure the engine or an AirPlay announcement destination."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, dict[str, str]] = {}

    async def async_step_user(self, user_input=None):
        """Choose the WakeMesh component to configure."""
        return self.async_show_menu(
            step_id="user", menu_options=["speaker", "engine"]
        )

    async def async_step_engine(self, user_input=None):
        """Connect to a WakeMesh Engine."""
        errors = {}
        if user_input is not None:
            client = RouterApiClient(
                async_get_clientsession(self.hass),
                user_input[CONF_URL],
                user_input[CONF_TOKEN],
            )
            try:
                await client.health()
            except RouterApiError as err:
                LOGGER.error(
                    "Unable to connect to WakeMesh at %s: %s",
                    user_input[CONF_URL],
                    err,
                )
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    f"engine:{user_input[CONF_URL].rstrip('/')}"
                )
                self._abort_if_unique_id_configured()
                data = dict(user_input)
                data[CONF_ENTRY_TYPE] = ENTRY_TYPE_ENGINE
                return self.async_create_entry(title="WakeMesh Engine", data=data)

        return self.async_show_form(
            step_id="engine",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=DEFAULT_URL): str,
                    vol.Optional(CONF_TOKEN, default=""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_speaker(self, user_input: dict[str, Any] | None = None):
        """Discover and add a HomePod or stereo pair."""
        if user_input is not None:
            discovered = self._discovered.get(user_input[CONF_DESTINATION])
            if discovered:
                identifier = discovered[CONF_IDENTIFIER]
                await self.async_set_unique_id(f"speaker:{identifier.lower()}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=discovered[CONF_NAME], data=discovered
                )

        options = await self._async_discover_speakers()
        if not options:
            return await self.async_step_manual_speaker()

        return self.async_show_form(
            step_id="speaker",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DESTINATION): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def _async_discover_speakers(self) -> list[selector.SelectOptionDict]:
        """Discover HomePods and collapse only genuine stereo pairs."""
        devices = await pyatv.scan(self.hass.loop, timeout=5)
        grouped: dict[str, list[tuple[Any, dict[str, str]]]] = defaultdict(list)
        for device in devices:
            airplay = device.get_service(Protocol.AirPlay)
            raop = device.get_service(Protocol.RAOP)
            if not airplay or not raop:
                continue
            properties = dict(airplay.properties)
            identifier = properties.get("deviceid")
            if not identifier or not properties.get("model", "").startswith(
                "AudioAccessory"
            ):
                continue
            grouped[properties.get("tsid") or identifier].append((device, properties))

        configured_ids = {
            entry.unique_id.removeprefix("speaker:")
            for entry in self._async_current_entries()
            if entry.unique_id and entry.unique_id.startswith("speaker:")
        }
        options: list[selector.SelectOptionDict] = []
        for members in grouped.values():
            leader, properties = next(
                (member for member in members if member[1].get("igl") == "1"),
                members[0],
            )
            identifier = properties["deviceid"]
            if identifier.lower() in configured_ids:
                continue
            source_entity = self._find_source_entity(identifier, str(leader.address))
            if not source_entity:
                continue
            name = properties.get("gpn") or leader.name
            count = len(members)
            kind = f"stereo pair, {count} speakers" if count > 1 else "single speaker"
            self._discovered[identifier] = {
                CONF_ENTRY_TYPE: ENTRY_TYPE_SPEAKER,
                CONF_NAME: f"{name} WakeMesh",
                CONF_IDENTIFIER: identifier,
                CONF_SOURCE_ENTITY: source_entity,
            }
            options.append(
                selector.SelectOptionDict(
                    value=identifier, label=f"{name} — {kind}"
                )
            )
        return sorted(options, key=lambda option: option["label"].lower())

    def _find_source_entity(self, identifier: str, address: str) -> str | None:
        """Match a discovered endpoint to its native Apple media player."""
        config_entry_id = next(
            (
                entry.entry_id
                for entry in self.hass.config_entries.async_entries("apple_tv")
                if str(entry.data.get("address")) == address
                or (entry.unique_id and entry.unique_id.lower() == identifier.lower())
            ),
            None,
        )
        if not config_entry_id:
            return None
        entity_registry = er.async_get(self.hass)
        return next(
            (
                entity.entity_id
                for entity in entity_registry.entities.values()
                if entity.config_entry_id == config_entry_id
                and entity.domain == "media_player"
                and entity.platform == "apple_tv"
            ),
            None,
        )

    async def async_step_manual_speaker(self, user_input=None):
        """Provide a fallback for unusual AirPlay environments."""
        if user_input is not None:
            identifier = user_input[CONF_IDENTIFIER]
            await self.async_set_unique_id(f"speaker:{identifier.lower()}")
            self._abort_if_unique_id_configured()
            data = dict(user_input)
            data[CONF_ENTRY_TYPE] = ENTRY_TYPE_SPEAKER
            return self.async_create_entry(title=data[CONF_NAME], data=data)

        return self.async_show_form(
            step_id="manual_speaker",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_IDENTIFIER): str,
                    vol.Required(CONF_SOURCE_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="media_player")
                    ),
                }
            ),
        )
