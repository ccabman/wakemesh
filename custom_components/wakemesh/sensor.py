"""Status sensors for WakeMesh."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Add router health sensors."""
    coordinator = entry.runtime_data["coordinator"]
    async_add_entities(
        [
            WakeMeshWorkerSensor(coordinator, entry.entry_id, "workers", False),
            WakeMeshWorkerSensor(coordinator, entry.entry_id, "running_workers", True),
        ]
    )


class WakeMeshWorkerSensor(CoordinatorEntity, SensorEntity):
    """Count configured or currently running WakeMesh workers."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "workers"

    def __init__(self, coordinator, entry_id: str, key: str, running_only: bool) -> None:
        super().__init__(coordinator)
        self._running_only = running_only
        self._attr_name = "Running workers" if running_only else "Workers"
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="WakeMesh Engine",
            manufacturer="WakeMesh",
            model="Audio processor/router",
        )

    @property
    def native_value(self) -> int:
        workers = self.coordinator.data.get("workers", {}).values()
        if self._running_only:
            return sum(1 for worker in workers if worker.get("running"))
        return len(list(workers))

    @property
    def extra_state_attributes(self) -> dict:
        return {"workers": self.coordinator.data.get("workers", {})}
