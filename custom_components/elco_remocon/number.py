"""Number entities for Elco Remocon-Net (gas boiler setpoints)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ITEM_DHW_TEMP,
    ITEM_VIRT_FLOW_OFFSET,
    ITEM_VIRT_FLOW_SETPOINT,
    ITEM_VIRT_REDUCED_TEMP,
    ITEM_ZONE_ECONOMY_TEMP,
)
from .coordinator import ElcoRemoconCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(kw_only=True)
class ElcoNumberDescription(NumberEntityDescription):
    """Describe an Elco number entity."""

    item_ids: tuple[str, ...]
    setter: str
    native_unit_of_measurement: str | None = None
    device_class: NumberDeviceClass | None = None
    entity_category: EntityCategory | None = None


NUMBERS: tuple[ElcoNumberDescription, ...] = (
    ElcoNumberDescription(
        key="flow_setpoint",
        translation_key="flow_setpoint",
        item_ids=(ITEM_VIRT_FLOW_SETPOINT,),
        setter="set_flow_setpoint",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.BOX,
    ),
    ElcoNumberDescription(
        key="flow_offset",
        translation_key="flow_offset",
        item_ids=(ITEM_VIRT_FLOW_OFFSET,),
        setter="set_flow_offset",
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    ElcoNumberDescription(
        key="reduced_temperature",
        translation_key="reduced_temperature",
        item_ids=(ITEM_VIRT_REDUCED_TEMP, ITEM_ZONE_ECONOMY_TEMP),
        setter="set_boiler_reduced_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.BOX,
    ),
    ElcoNumberDescription(
        key="dhw_temperature",
        translation_key="dhw_temperature",
        item_ids=(ITEM_DHW_TEMP,),
        setter="set_dhw_setpoint",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        mode=NumberMode.BOX,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Elco number entities (gas boilers only)."""
    coordinator: ElcoRemoconCoordinator = hass.data[DOMAIN][entry.entry_id]
    if not (coordinator.data and coordinator.data.is_gas_boiler):
        return
    gw_id = entry.data["gateway_id"]
    entities = [
        ElcoNumber(coordinator, gw_id, desc)
        for desc in NUMBERS
        if any(item_id in coordinator.data.items for item_id in desc.item_ids)
    ]
    async_add_entities(entities)


class ElcoNumber(CoordinatorEntity[ElcoRemoconCoordinator], NumberEntity):
    """Elco number entity backed by a BSB data item."""

    _attr_has_entity_name = True
    entity_description: ElcoNumberDescription
    _attr_native_step = 1.0

    def __init__(
        self,
        coordinator: ElcoRemoconCoordinator,
        gw_id: str,
        description: ElcoNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{gw_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, gw_id)},
            "name": "Remocon-Net Boiler",
            "manufacturer": "Elco",
            "model": "Gas boiler",
        }

    @property
    def _item_id(self) -> str | None:
        for item_id in self.entity_description.item_ids:
            if item_id in self.coordinator.data.items:
                return item_id
        return None

    @property
    def _meta(self) -> dict:
        item_id = self._item_id
        return self.coordinator.data.item_meta(item_id) if item_id else {}

    @property
    def available(self) -> bool:
        return super().available and self._item_id is not None

    @property
    def native_value(self) -> float | None:
        item_id = self._item_id
        return self.coordinator.data.item_value(item_id) if item_id else None

    @property
    def native_min_value(self) -> float:
        return float(self._meta.get("min", 0))

    @property
    def native_max_value(self) -> float:
        meta = self._meta
        return float(meta.get("max", 100))

    @property
    def native_step(self) -> float:
        return float(self._meta.get("step", 1.0)) or 1.0

    async def async_set_native_value(self, value: float) -> None:
        """Set the data item value."""
        setter = getattr(self.coordinator.client, self.entity_description.setter)
        await self.hass.async_add_executor_job(setter, value)
        await self.coordinator.async_request_refresh()
