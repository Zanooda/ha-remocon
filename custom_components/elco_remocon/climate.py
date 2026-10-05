"""Climate entity for Elco Remocon-Net."""

from __future__ import annotations

import logging

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MODE_AUTOMATIC,
    MODE_COMFORT,
    MODE_PROTECTION,
    MODE_REDUCTION,
    PLANT_MODE_HEATING_ONLY,
    PLANT_MODE_OFF,
    PLANT_MODE_SUMMER,
    PLANT_MODE_WINTER,
)
from .coordinator import ElcoRemoconCoordinator

_LOGGER = logging.getLogger(__name__)

PRESET_COMFORT = "comfort"
PRESET_REDUCED = "reduced"

HVAC_MODE_MAP = {
    MODE_PROTECTION: HVACMode.OFF,
    MODE_AUTOMATIC: HVACMode.AUTO,
    MODE_REDUCTION: HVACMode.HEAT,
    MODE_COMFORT: HVACMode.HEAT,
}

# Gas boiler: map the plant operation mode onto HA HVAC modes. Summer and OFF
# both stop heating, so both map to OFF; the full four-way choice is available
# through the operation mode select entity.
BOILER_HVAC_MODE_MAP = {
    PLANT_MODE_OFF: HVACMode.OFF,
    PLANT_MODE_SUMMER: HVACMode.OFF,
    PLANT_MODE_HEATING_ONLY: HVACMode.HEAT,
    PLANT_MODE_WINTER: HVACMode.AUTO,
}

BOILER_HVAC_TO_PLANT = {
    HVACMode.OFF: PLANT_MODE_OFF,
    HVACMode.HEAT: PLANT_MODE_HEATING_ONLY,
    HVACMode.AUTO: PLANT_MODE_WINTER,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Elco climate entity."""
    coordinator: ElcoRemoconCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ElcoClimateEntity(coordinator, entry)])


class ElcoClimateEntity(CoordinatorEntity[ElcoRemoconCoordinator], ClimateEntity):
    """Climate entity for an Elco heating zone."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(
        self,
        coordinator: ElcoRemoconCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        gw_id = entry.data["gateway_id"]
        self._gw_id = gw_id
        self._attr_unique_id = f"{gw_id}_climate_zone_{entry.data.get('zone', '1')}"

        is_boiler = bool(coordinator.data and coordinator.data.is_gas_boiler)
        self._is_boiler = is_boiler
        if is_boiler:
            self._attr_translation_key = "elco_boiler"
            self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
            self._attr_preset_modes = []
            self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
            model = "Gas boiler"
            name = "Remocon-Net Boiler"
        else:
            self._attr_translation_key = "elco_heat_pump"
            self._attr_supported_features = (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.PRESET_MODE
            )
            self._attr_preset_modes = [PRESET_COMFORT, PRESET_REDUCED]
            self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.AUTO, HVACMode.OFF]
            model = "Aerotop SPK"
            name = "Remocon-Net Heat Pump"

        self._attr_device_info = {
            "identifiers": {(DOMAIN, gw_id)},
            "name": name,
            "manufacturer": "Elco",
            "model": model,
        }

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        data = self.coordinator.data
        if data.room_temp > 0:
            return data.room_temp
        if self._is_boiler:
            # No room sensor: the boiler has no measured temperature.
            return None
        return data.desired_temp if data.desired_temp > 0 else None

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        data = self.coordinator.data
        return data.comfort_temp if data.comfort_temp > 0 else None

    @property
    def target_temperature_step(self) -> float:
        """Return temperature step."""
        return self.coordinator.data.comfort_temp_step or 0.5

    @property
    def min_temp(self) -> float:
        """Return min temperature."""
        return self.coordinator.data.comfort_temp_min or 5.0

    @property
    def max_temp(self) -> float:
        """Return max temperature."""
        return self.coordinator.data.comfort_temp_max or 35.0

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        data = self.coordinator.data
        if self._is_boiler:
            if data.plant_mode is None:
                return HVACMode.AUTO
            return BOILER_HVAC_MODE_MAP.get(data.plant_mode, HVACMode.AUTO)
        return HVAC_MODE_MAP.get(data.zone_mode, HVACMode.AUTO)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        data = self.coordinator.data
        if self._is_boiler:
            if data.plant_mode == PLANT_MODE_OFF:
                return HVACAction.OFF
            if data.flame_sensor or data.heat_request:
                return HVACAction.HEATING
            return HVACAction.IDLE
        if data.zone_mode == MODE_PROTECTION:
            return HVACAction.OFF
        if data.heating_active:
            return HVACAction.HEATING
        if data.cooling_active:
            return HVACAction.COOLING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        """Return current preset mode."""
        if self._is_boiler:
            return None
        data = self.coordinator.data
        if data.zone_mode == MODE_COMFORT:
            return PRESET_COMFORT
        if data.zone_mode == MODE_REDUCTION:
            return PRESET_REDUCED
        return None

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        if self._is_boiler:
            await self.hass.async_add_executor_job(
                self.coordinator.client.set_boiler_comfort_temperature, temperature
            )
        else:
            await self.hass.async_add_executor_job(
                self.coordinator.client.set_zone_temperatures, temperature, None
            )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        if self._is_boiler:
            mode = BOILER_HVAC_TO_PLANT.get(hvac_mode)
            if mode is None:
                return
            await self.hass.async_add_executor_job(
                self.coordinator.client.set_plant_mode, mode
            )
            await self.coordinator.async_request_refresh()
            return

        mode_map = {
            HVACMode.OFF: MODE_PROTECTION,
            HVACMode.AUTO: MODE_AUTOMATIC,
            HVACMode.HEAT: MODE_COMFORT,
        }
        mode = mode_map.get(hvac_mode)
        if mode is None:
            return
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_zone_mode, mode
        )
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if self._is_boiler:
            return
        mode_map = {
            PRESET_COMFORT: MODE_COMFORT,
            PRESET_REDUCED: MODE_REDUCTION,
        }
        mode = mode_map.get(preset_mode)
        if mode is None:
            return
        await self.hass.async_add_executor_job(
            self.coordinator.client.set_zone_mode, mode
        )
        await self.coordinator.async_request_refresh()
