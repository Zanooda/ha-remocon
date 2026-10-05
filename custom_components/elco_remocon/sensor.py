"""Sensor entities for Elco Remocon-Net."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import RemoconData
from .const import DOMAIN
from .coordinator import ElcoRemoconCoordinator


@dataclass(kw_only=True)
class ElcoSensorDescription(SensorEntityDescription):
    """Describe an Elco sensor entity."""

    key: str
    translation_key: str
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    native_unit_of_measurement: str | None = None
    entity_category: EntityCategory | None = None
    suggested_display_precision: int = 1
    value_fn: Callable[[RemoconData], StateType]
    exists_fn: Callable[[RemoconData], bool] = lambda _: True


SENSORS: tuple[ElcoSensorDescription, ...] = (
    ElcoSensorDescription(
        key="outside_temp",
        translation_key="outside_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.outside_temp,
    ),
    ElcoSensorDescription(
        key="desired_temp",
        translation_key="desired_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.desired_temp if d.desired_temp > 0 else None,
    ),
    ElcoSensorDescription(
        key="reduced_temp",
        translation_key="reduced_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.reduced_temp if d.reduced_temp > 0 else None,
    ),
    ElcoSensorDescription(
        key="flow_temp",
        translation_key="flow_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.flow_temperature,
        exists_fn=lambda d: d.flow_temperature is not None,
    ),
    ElcoSensorDescription(
        key="system_pressure",
        translation_key="system_pressure",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.system_pressure,
        exists_fn=lambda d: d.system_pressure is not None,
    ),
    ElcoSensorDescription(
        key="dhw_temp",
        translation_key="dhw_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: d.dhw_temp if d.dhw_temp > 0 else None,
        exists_fn=lambda d: d.has_dhw if d.is_gas_boiler else d.dhw_enabled,
    ),
    ElcoSensorDescription(
        key="ch_flow_setpoint",
        translation_key="ch_flow_setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.ch_flow_setpoint,
        exists_fn=lambda d: d.is_gas_boiler and d.ch_flow_setpoint is not None,
    ),
    ElcoSensorDescription(
        key="gas_heating_month",
        translation_key="gas_heating_month",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d.gas_heating_month,
        exists_fn=lambda d: d.is_gas_boiler and d.gas_heating_month is not None,
    ),
    ElcoSensorDescription(
        key="gas_dhw_month",
        translation_key="gas_dhw_month",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value_fn=lambda d: d.gas_dhw_month,
        exists_fn=lambda d: d.is_gas_boiler and d.gas_dhw_month is not None,
    ),
    ElcoSensorDescription(
        key="boiler_electricity_month",
        translation_key="boiler_electricity_month",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.boiler_electricity_month,
        exists_fn=lambda d: d.is_gas_boiler and d.boiler_electricity_month is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Elco sensors."""
    coordinator: ElcoRemoconCoordinator = hass.data[DOMAIN][entry.entry_id]
    gw_id = entry.data["gateway_id"]

    entities = [
        ElcoSensor(coordinator, gw_id, desc)
        for desc in SENSORS
        if desc.exists_fn(coordinator.data)
    ]
    async_add_entities(entities)


class ElcoSensor(CoordinatorEntity[ElcoRemoconCoordinator], SensorEntity):
    """Elco sensor entity."""

    _attr_has_entity_name = True
    entity_description: ElcoSensorDescription

    def __init__(
        self,
        coordinator: ElcoRemoconCoordinator,
        gw_id: str,
        description: ElcoSensorDescription,
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
    def native_value(self) -> StateType:
        """Return sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
