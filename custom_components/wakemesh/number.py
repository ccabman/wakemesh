"""Live AirPlay announcement volume controls for WakeMesh."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_IDLE_ANNOUNCEMENT_VOLUME,
    CONF_PLAYING_VOLUME_BOOST,
    DEFAULT_IDLE_ANNOUNCEMENT_VOLUME,
    DEFAULT_PLAYING_VOLUME_BOOST,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create adjustable volume controls for a RAOP endpoint."""
    async_add_entities(
        [
            RaopVolumeNumber(
                entry,
                CONF_PLAYING_VOLUME_BOOST,
                "Playing Announcement Boost",
                DEFAULT_PLAYING_VOLUME_BOOST,
                0,
                50,
            ),
            RaopVolumeNumber(
                entry,
                CONF_IDLE_ANNOUNCEMENT_VOLUME,
                "Idle Announcement Volume",
                DEFAULT_IDLE_ANNOUNCEMENT_VOLUME,
                0,
                100,
            ),
        ]
    )


class RaopVolumeNumber(NumberEntity):
    """A persisted, immediately effective RAOP volume setting."""

    _attr_has_entity_name = False
    _attr_native_step = 1.0
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        entry: ConfigEntry,
        key: str,
        name: str,
        default: float,
        minimum: float,
        maximum: float,
    ) -> None:
        self._entry = entry
        self._key = key
        self._default = default
        self._attr_name = f"{entry.title} {name}"
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="WakeMesh",
            model="AirPlay announcement destination",
        )

    @property
    def native_value(self) -> float:
        return float(self._entry.options.get(self._key, self._default))

    async def async_set_native_value(self, value: float) -> None:
        options = dict(self._entry.options)
        options[self._key] = float(value)
        self.hass.config_entries.async_update_entry(self._entry, options=options)
        self.async_write_ha_state()
