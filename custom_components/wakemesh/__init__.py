"""WakeMesh integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import RouterApiClient
from .const import CONF_TOKEN

PLATFORMS = ["sensor"]
LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the router API client."""
    client = RouterApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data.get(CONF_TOKEN, ""),
    )
    coordinator = DataUpdateCoordinator(
        hass,
        logger=LOGGER,
        name="WakeMesh status",
        update_method=client.status,
        update_interval=timedelta(seconds=15),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = {"client": client, "coordinator": coordinator}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the router client."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
