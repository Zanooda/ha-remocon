"""Binary sensor entities for Elco Remocon-Net."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RemoconData
from .const import DOMAIN
from .coordinator import ElcoRemoconCoordinator


@dataclass(kw_only=True)
class ElcoBinarySensorDescription(BinarySensorEntityDescription):
    """Describe an Elco binary sensor entity."""

    key: str
    translation_key: str
    device_class: BinarySensorDeviceClass | None = None
    value_fn: Callable[[RemoconData], bool]
    exists_fn: Callable[[RemoconData], bool] = lambda _: True


BINARY_SENSORS: tuple[ElcoBinarySensorDescription, ...] = (
    ElcoBinarySensorDescription(
        key="heating_active",
        translation_key="heating_active",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda d: d.heating_active,
        exists_fn=lambda d: not d.is_gas_boiler,
    ),
    ElcoBinarySensorDescription(
        key="cooling_active",
        translation_key="cooling_active",
        device_class=BinarySensorDeviceClass.COLD,
        value_fn=lambda d: d.cooling_active,
        exists_fn=lambda d: not d.is_gas_boiler,
    ),
    ElcoBinarySensorDescription(
        key="heat_pump_on",
        translation_key="heat_pump_on",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.heat_pump_on,
        exists_fn=lambda d: not d.is_gas_boiler,
    ),
    ElcoBinarySensorDescription(
        key="dhw_enabled",
        translation_key="dhw_enabled",
        value_fn=lambda d: d.dhw_enabled,
        exists_fn=lambda d: d.dhw_enabled or not d.is_gas_boiler,
    ),
    ElcoBinarySensorDescription(
        key="flame_on",
        translation_key="flame_on",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: d.flame_sensor,
        exists_fn=lambda d: d.is_gas_boiler,
    ),
    ElcoBinarySensorDescription(
        key="heat_request",
        translation_key="heat_request",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda d: d.heat_request,
        exists_fn=lambda d: d.is_gas_boiler,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Elco binary sensors."""
    coordinator: ElcoRemoconCoordinator = hass.data[DOMAIN][entry.entry_id]
    gw_id = entry.data["gateway_id"]

    entities = [
        ElcoBinarySensor(coordinator, gw_id, desc)
        for desc in BINARY_SENSORS
        if desc.exists_fn(coordinator.data)
    ]
    async_add_entities(entities)


class ElcoBinarySensor(CoordinatorEntity[ElcoRemoconCoordinator], BinarySensorEntity):
    """Elco binary sensor entity."""

    _attr_has_entity_name = True
    entity_description: ElcoBinarySensorDescription

    def __init__(
        self,
        coordinator: ElcoRemoconCoordinator,
        gw_id: str,
        description: ElcoBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{gw_id}_{description.key}"
        is_boiler = bool(coordinator.data and coordinator.data.is_gas_boiler)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, gw_id)},
            "name": "Remocon-Net Boiler" if is_boiler else "Remocon-Net Heat Pump",
            "manufacturer": "Elco",
            "model": "Gas boiler" if is_boiler else "Aerotop SPK",
        }

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return self.entity_description.value_fn(self.coordinator.data)
