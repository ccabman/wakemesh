"""Config flow for WakeMesh."""

from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RouterApiClient, RouterApiError
from .const import CONF_TOKEN, DEFAULT_URL, DOMAIN

LOGGER = logging.getLogger(__name__)


class WakeMeshConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure a local router app."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            client = RouterApiClient(
                async_get_clientsession(self.hass),
                user_input[CONF_URL],
                user_input[CONF_TOKEN],
            )
            try:
                health = await client.health()
            except RouterApiError as err:
                LOGGER.error("Unable to connect to WakeMesh at %s: %s", user_input[CONF_URL], err)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(user_input[CONF_URL].rstrip("/"))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="WakeMesh",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_URL, default=DEFAULT_URL): str,
                vol.Optional(CONF_TOKEN, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
