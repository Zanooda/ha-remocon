"""Select entities for Elco Remocon-Net (gas boiler operation modes)."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BOILER_TO_ZONE_MODE,
    DHW_ITEM_TO_MODE,
    DHW_MODE_TO_ITEM,
    DOMAIN,
    OPERATION_MODE_TO_PLANT,
    PLANT_TO_OPERATION_MODE,
    ZONE_MODE_TO_BOILER,
)
from .coordinator import ElcoRemoconCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Elco select entities (gas boilers only)."""
    coordinator: ElcoRemoconCoordinator = hass.data[DOMAIN][entry.entry_id]
    if not (coordinator.data and coordinator.data.is_gas_boiler):
        return
    gw_id = entry.data["gateway_id"]
    entities: list[SelectEntity] = [
        ElcoOperationModeSelect(coordinator, gw_id),
        ElcoZoneModeSelect(coordinator, gw_id),
    ]
    if coordinator.data.has_dhw:
        entities.append(ElcoDhwModeSelect(coordinator, gw_id))
    async_add_entities(entities)


class _ElcoBoilerSelect(CoordinatorEntity[ElcoRemoconCoordinator], SelectEntity):
    """Base select entity for a gas boiler."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ElcoRemoconCoordinator, gw_id: str) -> None:
        super().__init__(coordinator)
        self._gw_id = gw_id
        self._attr_device_info = {
            "identifiers": {(DOMAIN, gw_id)},
            "name": "Remocon-Net Boiler",
            "manufacturer": "Elco",
            "model": "Gas boiler",
        }


class ElcoOperationModeSelect(_ElcoBoilerSelect):
    """Plant operation mode (summer / winter / heating only / off)."""

    _attr_translation_key = "operation_mode"
    _attr_options = list(OPERATION_MODE_TO_PLANT)

    def __init__(self, coordinator: ElcoRemoconCoordinator, gw_id: str) -> None:
        super().__init__(coordinator, gw_id)
        self._attr_unique_id = f"{gw_id}_operation_mode"

    @property
    def current_option(self) -> str | None:
        """Return the current operation mode."""
        plant_mode = self.coordinator.data.plant_mode
        if plant_mode is None:
            return None
        return PLANT_TO_OPERATION_MODE.get(plant_mode)

    async def async_select_option(self, option: str) -> None:
        """Set the operation mode."""
        plant_mode = OPERATION_MODE_TO_PLANT.get(option)
        if plant_mode is None:
            return
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_plant_mode, plant_mode
        )
        await self.coordinator.async_request_refresh()


class ElcoZoneModeSelect(_ElcoBoilerSelect):
    """Zone mode (manual / time program)."""

    _attr_translation_key = "zone_mode"
    _attr_options = list(ZONE_MODE_TO_BOILER)

    def __init__(self, coordinator: ElcoRemoconCoordinator, gw_id: str) -> None:
        super().__init__(coordinator, gw_id)
        self._attr_unique_id = f"{gw_id}_zone_mode"

    @property
    def current_option(self) -> str | None:
        """Return the current zone mode."""
        zone_mode = self.coordinator.data.boiler_zone_mode
        if zone_mode is None:
            return None
        return BOILER_TO_ZONE_MODE.get(zone_mode)

    async def async_select_option(self, option: str) -> None:
        """Set the zone mode."""
        zone_mode = ZONE_MODE_TO_BOILER.get(option)
        if zone_mode is None:
            return
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_boiler_zone_mode, zone_mode
        )
        await self.coordinator.async_request_refresh()


class ElcoDhwModeSelect(_ElcoBoilerSelect):
    """Domestic hot water mode (disabled / time based / always active)."""

    _attr_translation_key = "dhw_mode"
    _attr_options = list(DHW_MODE_TO_ITEM)

    def __init__(self, coordinator: ElcoRemoconCoordinator, gw_id: str) -> None:
        super().__init__(coordinator, gw_id)
        self._attr_unique_id = f"{gw_id}_dhw_mode"

    @property
    def current_option(self) -> str | None:
        """Return the current DHW mode."""
        return DHW_ITEM_TO_MODE.get(self.coordinator.data.dhw_mode)

    async def async_select_option(self, option: str) -> None:
        """Set the DHW mode."""
        mode = DHW_MODE_TO_ITEM.get(option)
        if mode is None:
            return
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_boiler_dhw_mode, mode
        )
        await self.coordinator.async_request_refresh()
