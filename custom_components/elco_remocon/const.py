"""Constants for the Elco Remocon-Net integration."""

DOMAIN = "elco_remocon"
CONF_GATEWAY_ID = "gateway_id"
CONF_ZONE = "zone"

DEFAULT_ZONE = "1"
DEFAULT_SCAN_INTERVAL = 120

# API mode values (heat pump zone mode)
MODE_PROTECTION = 0
MODE_AUTOMATIC = 1
MODE_REDUCTION = 2
MODE_COMFORT = 3

# Plant operation modes (gas boiler "PlantMode" data item)
PLANT_MODE_SUMMER = 0
PLANT_MODE_WINTER = 1
PLANT_MODE_HEATING_ONLY = 2
PLANT_MODE_OFF = 5

# Stable option keys for the operation mode select entity
OPERATION_SUMMER = "summer"
OPERATION_WINTER = "winter"
OPERATION_HEATING_ONLY = "heating_only"
OPERATION_OFF = "off"

OPERATION_MODE_TO_PLANT = {
    OPERATION_SUMMER: PLANT_MODE_SUMMER,
    OPERATION_WINTER: PLANT_MODE_WINTER,
    OPERATION_HEATING_ONLY: PLANT_MODE_HEATING_ONLY,
    OPERATION_OFF: PLANT_MODE_OFF,
}
PLANT_TO_OPERATION_MODE = {v: k for k, v in OPERATION_MODE_TO_PLANT.items()}

# Zone operating modes for gas boilers ("ZoneMode" data item)
BOILER_ZONE_MODE_MANUAL = 2
BOILER_ZONE_MODE_TIME_PROGRAM = 3

ZONE_MODE_MANUAL = "manual"
ZONE_MODE_TIME_PROGRAM = "time_program"

ZONE_MODE_TO_BOILER = {
    ZONE_MODE_MANUAL: BOILER_ZONE_MODE_MANUAL,
    ZONE_MODE_TIME_PROGRAM: BOILER_ZONE_MODE_TIME_PROGRAM,
}
BOILER_TO_ZONE_MODE = {v: k for k, v in ZONE_MODE_TO_BOILER.items()}

# Data item identifiers (v2 BSB data items used by gas boilers)
ITEM_PLANT_MODE = "PlantMode"
ITEM_OUTSIDE_TEMP = "OutsideTemp"
ITEM_AUTOMATIC_THERMOREGULATION = "AutomaticThermoregulation"
ITEM_CH_FLOW_SETPOINT = "ChFlowSetpointTemp"
ITEM_CH_FLOW_TEMP = "ChFlowTemp"
ITEM_HEATING_FLOW_TEMP = "HeatingFlowTemp"
ITEM_HEATING_CIRCUIT_PRESSURE = "HeatingCircuitPressure"
ITEM_ZONE_MODE = "ZoneMode"
ITEM_ZONE_DESIRED_TEMP = "ZoneDesiredTemp"
ITEM_ZONE_MEASURED_TEMP = "ZoneMeasuredTemp"
ITEM_ZONE_COMFORT_TEMP = "ZoneComfortTemp"
ITEM_ZONE_ECONOMY_TEMP = "ZoneEconomyTemp"
ITEM_VIRT_COMFORT_TEMP = "VirtComfortTemp"
ITEM_VIRT_REDUCED_TEMP = "VirtReducedTemp"
ITEM_VIRT_FLOW_SETPOINT = "VirtTempSetpointHeat"
ITEM_VIRT_FLOW_OFFSET = "VirtTempOffsetHeat"
ITEM_ZONE_HEAT_REQUEST = "ZoneHeatRequest"
ITEM_IS_FLAME_ON = "IsFlameOn"
ITEM_HOLIDAY = "Holiday"
