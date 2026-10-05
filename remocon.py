#!/usr/bin/env python3
"""
Elco Remocon-Net CLI — Read and control your Elco heating system from the terminal.

Supports reading temperatures, operation modes, and system status, plus
setting zone temperatures, operation modes, and DHW settings via the
unofficial Remocon-Net cloud API. Works with both heat pumps (BSB
plantData/zoneData) and gas boilers (flat v2 data items).

Based on cschnidr/remocon-net-cli (read-only) and reverse-engineered
Ariston/Elco remotethermo.com API endpoints.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

import requests

# ============================================================================
# Constants
# ============================================================================

DEFAULT_BASE_URL = "https://www.remocon-net.remotethermo.com"

ZONE_MODES = {
    0: "Protection",
    1: "Automatic",
    2: "Reduction",
    3: "Comfort",
}

ZONE_MODE_MAP = {v.lower(): k for k, v in ZONE_MODES.items()}

BSB_ZONE_MODES = {
    0: "OFF",
    1: "TIME_PROGRAM",
    2: "MANUAL_NIGHT",
    3: "MANUAL",
}

DHW_MODES = {
    0: "OFF",
    1: "ON",
}

# Plant operation modes (gas boiler "PlantMode" data item)
PLANT_MODES = {
    0: "Summer",
    1: "Winter",
    2: "Heating only",
    5: "OFF",
}

PLANT_MODE_MAP = {
    "summer": 0,
    "winter": 1,
    "heating only": 2,
    "heating-only": 2,
    "heating_only": 2,
    "off": 5,
}

# Zone operating modes for gas boilers ("ZoneMode" data item)
BOILER_ZONE_MODES = {
    2: "Manual",
    3: "Time program",
}

BOILER_ZONE_MODE_MAP = {
    "manual": 2,
    "time program": 3,
    "time-program": 3,
    "time_program": 3,
}

# Data item identifiers (v2 BSB data items, used by gas boilers)
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

# Features payload used for v2 API calls — matches what the web UI sends.
# This may need adjustment depending on your specific heat pump model.
FEATURES_PAYLOAD = {
    "zones": [{"num": 1, "name": "", "roomSens": False, "geofenceDeroga": False,
               "virtInfo": None, "isHidden": False}],
    "solar": False, "convBoiler": False, "commBoiler": False, "hpSys": False,
    "hybridSys": False, "cascadeSys": False, "dhwProgSupported": True,
    "virtualZones": False, "hasVmc": False, "extendedTimeProg": False,
    "hasBoiler": True, "pilotSupported": False, "isVmcR2": False,
    "isEvo2": False, "dhwHidden": False, "dhwBoilerPresent": True,
    "dhwModeChangeable": True, "hvInputOff": False, "autoThermoReg": False,
    "hasMetering": False, "hasFireplace": False, "hasSlp": False,
    "hasEm20": False, "hasEm30": False, "systemServices": 0,
    "hasTwoCoolingTemp": False, "bmsActive": False, "hpCascadeSys": False,
    "hpCascadeConfig": -1, "bufferTimeProgAvailable": False,
    "distinctHeatCoolSetpoints": False, "hasZoneNames": False,
    "zoneManagerStandAlone": False, "hydraulicScheme": None,
    "preHeatingSupported": False, "hasGahp": False, "zigbeeActive": False,
    "hasSlpAloneOnBus": False, "isSlpCascade": False,
    "hasZeroColdWaterProg": False, "weatherProvider": 0,
    "hasDhwTimeProgTemperatures": 2, "isGSWHCommercialAloneOnBus": False,
}

# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Config:
    email: str
    password: str
    gateway_id: str
    zone_id: str = "1"
    base_url: str = DEFAULT_BASE_URL
    # MQTT
    mqtt_enabled: bool = False
    mqtt_host: Optional[str] = None
    mqtt_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_topic_prefix: str = "remocon/heating"
    mqtt_qos: int = 0
    mqtt_retain: bool = False


@dataclass
class HeatingData:
    current_temperature: float = 0.0
    desired_temperature: float = 0.0
    reduced_temperature: float = 0.0
    comfort_temperature: float = 0.0
    cool_comfort_temperature: Optional[float] = None
    cool_reduced_temperature: Optional[float] = None
    outside_temperature: float = 0.0
    operation_mode: str = "Unknown"
    operation_mode_value: int = 0
    heating_active: bool = False
    cooling_active: bool = False
    heat_or_cool_request: bool = False
    dhw_temperature: float = 0.0
    dhw_comfort_temp: Optional[float] = None
    dhw_reduced_temp: Optional[float] = None
    dhw_mode: str = "Unknown"
    dhw_enabled: bool = False
    boiler_status: str = "Unknown"
    heat_pump_on: bool = False
    system_pressure: Optional[float] = None
    flow_temperature: Optional[float] = None
    # Gas boiler (v2 BSB data items)
    is_gas_boiler: bool = False
    plant_mode: Optional[int] = None
    plant_mode_text: str = "Unknown"
    boiler_zone_mode: Optional[int] = None
    boiler_zone_mode_text: str = "Unknown"
    auto_thermoregulation: Optional[bool] = None
    ch_flow_setpoint: Optional[float] = None
    virt_flow_setpoint: Optional[float] = None
    virt_flow_offset: Optional[float] = None
    heat_request: bool = False
    flame_on: bool = False
    holiday: bool = False
    gas_heating_month: Optional[float] = None
    gas_dhw_month: Optional[float] = None
    boiler_electricity_month: Optional[float] = None
    zone_id: str = "1"
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "current_temperature": self.current_temperature,
            "desired_temperature": self.desired_temperature,
            "comfort_temperature": self.comfort_temperature,
            "reduced_temperature": self.reduced_temperature,
            "outside_temperature": self.outside_temperature,
            "operation_mode": self.operation_mode,
            "operation_mode_value": self.operation_mode_value,
            "heating_active": self.heating_active,
            "cooling_active": self.cooling_active,
            "dhw_temperature": self.dhw_temperature,
            "dhw_mode": self.dhw_mode,
            "dhw_enabled": self.dhw_enabled,
            "heat_pump_on": self.heat_pump_on,
            "system_pressure": self.system_pressure,
            "flow_temperature": self.flow_temperature,
            "is_gas_boiler": self.is_gas_boiler,
            "plant_mode": self.plant_mode,
            "plant_mode_text": self.plant_mode_text,
            "boiler_zone_mode": self.boiler_zone_mode,
            "boiler_zone_mode_text": self.boiler_zone_mode_text,
            "ch_flow_setpoint": self.ch_flow_setpoint,
            "virt_flow_setpoint": self.virt_flow_setpoint,
            "virt_flow_offset": self.virt_flow_offset,
            "heat_request": self.heat_request,
            "flame_on": self.flame_on,
            "holiday": self.holiday,
            "gas_heating_month": self.gas_heating_month,
            "gas_dhw_month": self.gas_dhw_month,
            "boiler_electricity_month": self.boiler_electricity_month,
            "zone_id": self.zone_id,
            "timestamp": self.timestamp.isoformat(),
        }


# ============================================================================
# Exceptions
# ============================================================================

class RemoconError(Exception):
    exit_code: int = 1
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

class ConfigError(RemoconError):
    exit_code: int = 4

class AuthError(RemoconError):
    exit_code: int = 3

class NetworkError(RemoconError):
    exit_code: int = 1

class DataError(RemoconError):
    exit_code: int = 2

class SessionExpiredError(RemoconError):
    exit_code: int = 3


# ============================================================================
# Configuration
# ============================================================================

def load_config_file(path: str) -> dict:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}")
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in config file: {e}")


def build_config(args: argparse.Namespace) -> Config:
    file_data = {}
    config_file = getattr(args, "config_file", None)
    if config_file:
        file_data = load_config_file(config_file)

    def _val(cli_attr, file_key, env_key):
        v = getattr(args, cli_attr, None)
        if v is not None:
            return v
        v = os.environ.get(env_key)
        if v is not None:
            return v
        v = file_data.get(file_key)
        return v

    email = _val("email", "email", "REMOCON_EMAIL")
    password = _val("password", "password", "REMOCON_PASSWORD")
    gateway_id = _val("gateway", "gateway_id", "REMOCON_GATEWAY")
    zone_id = _val("zone", "zone_id", "REMOCON_ZONE")

    missing = [f for f, v in [("email", email), ("password", password), ("gateway", gateway_id)] if not v]
    if missing:
        raise ConfigError(f"Missing required config: {', '.join(missing)}")

    return Config(
        email=email,
        password=password,
        gateway_id=gateway_id,
        zone_id=str(zone_id or "1"),
        base_url=file_data.get("base_url", DEFAULT_BASE_URL),
        mqtt_enabled=_val("mqtt_enabled", "mqtt_enabled", "REMOCON_MQTT_ENABLED") or False,
        mqtt_host=_val("mqtt_host", "mqtt_host", "REMOCON_MQTT_HOST"),
        mqtt_port=int(_val("mqtt_port", "mqtt_port", "REMOCON_MQTT_PORT") or 1883),
        mqtt_username=_val("mqtt_username", "mqtt_username", "REMOCON_MQTT_USER"),
        mqtt_password=_val("mqtt_password", "mqtt_password", "REMOCON_MQTT_PASS"),
        mqtt_topic_prefix=_val("mqtt_topic_prefix", "mqtt_topic_prefix", "REMOCON_MQTT_TOPIC") or "remocon/heating",
        mqtt_qos=int(_val("mqtt_qos", "mqtt_qos", "REMOCON_MQTT_QOS") or 0),
        mqtt_retain=bool(_val("mqtt_retain", "mqtt_retain", "REMOCON_MQTT_RETAIN")),
    )


# ============================================================================
# API Client
# ============================================================================

class RemoconClient:
    """Low-level API client for the Elco Remocon-Net cloud service."""

    def __init__(self, config: Config):
        self.config = config
        self.session: Optional[requests.Session] = None
        self._features: Optional[dict] = None
        self._comfort_item_id: str = ITEM_VIRT_COMFORT_TEMP
        self._reduced_item_id: str = ITEM_VIRT_REDUCED_TEMP
        self._is_gas_boiler: Optional[bool] = None

    def login(self) -> None:
        """Authenticate via the R2 web login (cookie-based session)."""
        s = requests.Session()
        url = f"{self.config.base_url}/R2/Account/Login?returnUrl=HTTP/2"
        payload = (
            f"Email={quote(self.config.email, safe='')}"
            f"&Password={quote(self.config.password, safe='')}"
            f"&RememberMe=false"
        )
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": "browserUtcOffset=-120",
        }
        try:
            resp = s.post(url, headers=headers, data=payload, timeout=15)
        except requests.RequestException as e:
            raise NetworkError(f"Connection failed: {e}")

        if resp.status_code in (401, 403):
            raise AuthError("Invalid email or password")
        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError:
            raise AuthError("Could not parse login response")

        if not data.get("ok"):
            raise AuthError(data.get("message", "Login failed"))

        self.session = s

    def _ensure_session(self) -> requests.Session:
        if self.session is None:
            self.login()
        return self.session  # type: ignore

    def _request(self, method: str, path: str, **kwargs) -> Any:
        s = self._ensure_session()
        url = f"{self.config.base_url}{path}"
        kwargs.setdefault("timeout", 15)
        try:
            resp = s.request(method, url, **kwargs)
        except requests.RequestException as e:
            raise NetworkError(f"Request failed: {e}")

        if resp.status_code in (401, 403):
            raise SessionExpiredError("Session expired, re-login needed")
        resp.raise_for_status()
        return resp.json()

    # ---- Read operations ----

    def _get_features(self) -> dict:
        """Fetch the plant's real feature set (cached)."""
        if self._features is not None:
            return self._features
        try:
            data = self._request(
                "GET", f"/R2/Plant/Features/{self.config.gateway_id}?eagerMode=false"
            )
            payload = data.get("data") or {}
            features = dict(payload.get("features") or {})
            plant = payload.get("plant") or {}
            if plant.get("gatewayId"):
                features["gatewayId"] = plant["gatewayId"]
            self._features = features or dict(FEATURES_PAYLOAD)
        except RemoconError:
            self._features = dict(FEATURES_PAYLOAD)
        return self._features

    def get_home_data(self, not_essentials: bool = False, real_features: bool = False) -> dict:
        """Fetch home data via the R2 API (plantData/zoneData or items[])."""
        path = f"/R2/PlantHome/GetData/{self.config.gateway_id}?umsys=si"
        payload = {
            "useCache": True,
            "zone": int(self.config.zone_id),
            "filter": {
                "notEssentials": not_essentials,
                "plant": True,
                "zone": True,
                "dhw": True,
            },
            "features": self._get_features() if real_features else FEATURES_PAYLOAD,
        }
        data = self._request("POST", path, json=payload)
        return data.get("data", data)

    def get_plant_data(self) -> dict:
        """Fetch plant + zone data via the legacy BSB API (heat pumps)."""
        path = f"/R2/PlantHomeBsb/GetData/{self.config.gateway_id}"
        payload = {
            "useCache": True,
            "zone": int(self.config.zone_id),
            "filter": {"progIds": None, "plant": True, "zone": True},
        }
        data = self._request("POST", path, json=payload)
        return data.get("data", data)

    def get_system_items(self, item_ids: list[dict]) -> dict:
        """Fetch specific data items via the v2 API."""
        path = f"/api/v2/remote/dataItems/{self.config.gateway_id}/get?umsys=si"
        payload = {
            "useCache": False,
            "items": item_ids,
            "features": FEATURES_PAYLOAD,
            "culture": "de",
        }
        data = self._request("POST", path, json=payload)
        result = {}
        for item in data.get("items", []):
            result[item["id"]] = item.get("value")
        return result

    def get_metering(self) -> dict:
        """Return current-month consumption in kWh from the metering API."""
        data = self._request(
            "POST",
            f"/R2/PlantMetering/GetData/{self.config.gateway_id}",
            json={},
            timeout=30,
        )
        payload = data.get("data") or {}
        as_kwh = payload.get("asKwh") or {}
        result: dict = {}
        for row in as_kwh.get("donutData") or []:
            if row.get("tab") != "ConsumedGas" or row.get("period") != "CurrentMonth":
                continue
            result[str(row.get("series", "")).lower()] = float(row.get("value") or 0)
        for row in as_kwh.get("boilerElectricity") or []:
            if row.get("period") == "CurrentMonth":
                result["electricity"] = float(row.get("value") or 0)
        return result

    def is_gas_boiler(self) -> bool:
        """Detect whether the plant is a gas boiler (item-based) or a heat pump."""
        if self._is_gas_boiler is None:
            probe = self.get_home_data()
            if "plantData" in probe or "zoneData" in probe:
                self._is_gas_boiler = False
            else:
                self._is_gas_boiler = bool(probe.get("items"))
        return self._is_gas_boiler

    def get_full_data(self) -> HeatingData:
        """Retrieve all available data and return a HeatingData object."""
        if not self.is_gas_boiler():
            return self._parse_heat_pump(self.get_home_data())

        raw = self.get_home_data(not_essentials=True, real_features=True)
        data = self._parse_gas_boiler(raw)
        try:
            metering = self.get_metering()
            data.gas_heating_month = metering.get("heating")
            data.gas_dhw_month = metering.get("dhw")
            data.boiler_electricity_month = metering.get("electricity")
        except RemoconError:
            pass
        return data

    def _parse_heat_pump(self, raw: dict) -> HeatingData:
        """Parse a heat-pump (plantData/zoneData) response."""
        plant = raw.get("plantData", {})
        zone = raw.get("zoneData", {})

        # Try to get system metrics via v2 API
        sys_items = {}
        try:
            sys_items = self.get_system_items([
                {"id": "HeatingCircuitPressure", "zn": 0},
                {"id": "ChFlowTemp", "zn": 0},
            ])
        except Exception:
            pass

        mode_info = zone.get("mode", {})
        mode_val = mode_info.get("value", 0)
        mode_texts = mode_info.get("allowedOptionTexts", list(ZONE_MODES.values()))
        if mode_val < len(mode_texts):
            mode_str = mode_texts[mode_val]
        else:
            mode_str = ZONE_MODES.get(mode_val, f"Mode {mode_val}")

        dhw_mode_info = plant.get("dhwMode", {})
        dhw_mode_val = dhw_mode_info.get("value", 0)
        dhw_mode_str = "Unknown"
        for opt in dhw_mode_info.get("options", []):
            if opt.get("value") == dhw_mode_val:
                dhw_mode_str = opt.get("text", "Unknown")

        pressure = sys_items.get("HeatingCircuitPressure")
        flow_temp = sys_items.get("ChFlowTemp")

        return HeatingData(
            current_temperature=float(zone.get("roomTemp", 0)),
            desired_temperature=float(zone.get("desiredRoomTemp", 0)),
            reduced_temperature=float(zone.get("chReducedTemp", {}).get("value", 0)),
            comfort_temperature=float(zone.get("chComfortTemp", {}).get("value", 0)),
            cool_comfort_temperature=_float_or_none(zone.get("coolComfortTemp", {}).get("value")),
            cool_reduced_temperature=_float_or_none(zone.get("coolReducedTemp", {}).get("value")),
            outside_temperature=float(plant.get("outsideTemp", 0)),
            operation_mode=mode_str,
            operation_mode_value=mode_val,
            heating_active=bool(zone.get("isHeatingActive", 0)),
            cooling_active=bool(zone.get("isCoolingActive", 0)),
            heat_or_cool_request=bool(zone.get("heatOrCoolRequest", 0)),
            dhw_temperature=float(plant.get("dhwStorageTemp", 0)),
            dhw_comfort_temp=_float_or_none(plant.get("dhwComfortTemp", {}).get("value")),
            dhw_reduced_temp=_float_or_none(plant.get("dhwReducedTemp", {}).get("value")),
            dhw_mode=dhw_mode_str,
            dhw_enabled=bool(plant.get("dhwEnabled", 0)),
            boiler_status="Running" if plant.get("flameSensor") else "Standby",
            heat_pump_on=bool(plant.get("heatPumpOn", 0)),
            system_pressure=float(pressure) if pressure is not None else None,
            flow_temperature=float(flow_temp) if flow_temp is not None else None,
            zone_id=self.config.zone_id,
            timestamp=datetime.now(),
        )

    def _parse_gas_boiler(self, raw: dict) -> HeatingData:
        """Parse a gas-boiler (flat items[]) response."""
        items = {item["id"]: item for item in raw.get("items") or []}

        def value(item_id: str):
            item = items.get(item_id)
            return item.get("value") if item else None

        comfort = items.get(ITEM_VIRT_COMFORT_TEMP) or items.get(ITEM_ZONE_COMFORT_TEMP)
        reduced = items.get(ITEM_VIRT_REDUCED_TEMP) or items.get(ITEM_ZONE_ECONOMY_TEMP)
        if comfort:
            self._comfort_item_id = comfort["id"]
        if reduced:
            self._reduced_item_id = reduced["id"]

        plant_mode = value(ITEM_PLANT_MODE)
        zone_mode = value(ITEM_ZONE_MODE)
        flow_temp = value(ITEM_CH_FLOW_TEMP)
        if flow_temp is None:
            flow_temp = value(ITEM_HEATING_FLOW_TEMP)
        heat_request = value(ITEM_ZONE_HEAT_REQUEST)

        return HeatingData(
            current_temperature=float(value(ITEM_ZONE_MEASURED_TEMP) or 0),
            desired_temperature=float(value(ITEM_ZONE_DESIRED_TEMP) or 0),
            reduced_temperature=float(reduced.get("value", 0)) if reduced else 0.0,
            comfort_temperature=float(comfort.get("value", 0)) if comfort else 0.0,
            outside_temperature=float(value(ITEM_OUTSIDE_TEMP) or 0),
            operation_mode=PLANT_MODES.get(int(plant_mode), "Unknown") if plant_mode is not None else "Unknown",
            operation_mode_value=int(plant_mode) if plant_mode is not None else 0,
            heating_active=bool(heat_request),
            cooling_active=False,
            heat_or_cool_request=bool(heat_request),
            dhw_temperature=0.0,
            dhw_mode="Unknown",
            dhw_enabled=False,
            boiler_status="Running" if value(ITEM_IS_FLAME_ON) else "Standby",
            heat_pump_on=bool(heat_request),
            system_pressure=_float_or_none(value(ITEM_HEATING_CIRCUIT_PRESSURE)),
            flow_temperature=_float_or_none(flow_temp),
            is_gas_boiler=True,
            plant_mode=int(plant_mode) if plant_mode is not None else None,
            plant_mode_text=PLANT_MODES.get(int(plant_mode), "Unknown") if plant_mode is not None else "Unknown",
            boiler_zone_mode=int(zone_mode) if zone_mode is not None else None,
            boiler_zone_mode_text=BOILER_ZONE_MODES.get(int(zone_mode), "Unknown") if zone_mode is not None else "Unknown",
            auto_thermoregulation=bool(value(ITEM_AUTOMATIC_THERMOREGULATION)) if value(ITEM_AUTOMATIC_THERMOREGULATION) is not None else None,
            ch_flow_setpoint=_float_or_none(value(ITEM_CH_FLOW_SETPOINT)),
            virt_flow_setpoint=_float_or_none(value(ITEM_VIRT_FLOW_SETPOINT)),
            virt_flow_offset=_float_or_none(value(ITEM_VIRT_FLOW_OFFSET)),
            heat_request=bool(heat_request),
            flame_on=bool(value(ITEM_IS_FLAME_ON)),
            holiday=bool(value(ITEM_HOLIDAY)),
            zone_id=self.config.zone_id,
            timestamp=datetime.now(),
        )

    # ---- Write operations (via v2 REST API) ----

    def set_zone_temperatures(
        self,
        comfort: Optional[float] = None,
        reduced: Optional[float] = None,
        is_cooling: bool = False,
    ) -> bool:
        """Set comfort and/or reduced temperature for a zone."""
        # First, read current values
        raw = self.get_plant_data()
        zone = raw.get("zoneData", {})

        if is_cooling:
            old_comf = float(zone.get("coolComfortTemp", {}).get("value", 0))
            old_econ = float(zone.get("coolReducedTemp", {}).get("value", 0))
        else:
            old_comf = float(zone.get("chComfortTemp", {}).get("value", 0))
            old_econ = float(zone.get("chReducedTemp", {}).get("value", 0))

        new_comf = comfort if comfort is not None else old_comf
        new_econ = reduced if reduced is not None else old_econ

        path = (
            f"/api/v2/remote/bsbZones/{self.config.gateway_id}"
            f"/{self.config.zone_id}/temperatures?isCooling={'true' if is_cooling else 'false'}"
        )
        payload = {
            "new": {"comf": new_comf, "econ": new_econ},
            "old": {"comf": old_comf, "econ": old_econ},
        }
        self._request("POST", path, json=payload)
        return True

    def set_zone_mode(self, mode: str, is_cooling: bool = False) -> bool:
        """Set the zone operation mode. Accepts: protection, automatic, reduction, comfort."""
        mode_lower = mode.lower()
        if mode_lower not in ZONE_MODE_MAP:
            raise DataError(
                f"Invalid mode '{mode}'. Valid modes: {', '.join(ZONE_MODE_MAP.keys())}"
            )
        new_mode = ZONE_MODE_MAP[mode_lower]

        # Read current mode
        raw = self.get_plant_data()
        old_mode = raw.get("zoneData", {}).get("mode", {}).get("value", 1)

        path = (
            f"/api/v2/remote/bsbZones/{self.config.gateway_id}"
            f"/{self.config.zone_id}/mode?isCooling={'true' if is_cooling else 'false'}"
        )
        payload = {"new": new_mode, "old": old_mode}
        self._request("POST", path, json=payload)
        return True

    def set_dhw_temperature(
        self,
        comfort: Optional[float] = None,
        reduced: Optional[float] = None,
    ) -> bool:
        """Set domestic hot water comfort/reduced temperature."""
        raw = self.get_plant_data()
        plant = raw.get("plantData", {})

        old_comf = float(plant.get("dhwComfortTemp", {}).get("value", 45))
        old_econ = float(plant.get("dhwReducedTemp", {}).get("value", 40))

        new_comf = comfort if comfort is not None else old_comf
        new_econ = reduced if reduced is not None else old_econ

        path = f"/api/v2/remote/bsbPlantData/{self.config.gateway_id}/dhwTemp"
        payload = {
            "new": {"comf": new_comf, "econ": new_econ},
            "old": {"comf": old_comf, "econ": old_econ},
        }
        self._request("POST", path, json=payload)
        return True

    def set_dhw_mode(self, mode: str) -> bool:
        """Set DHW mode: 'on' or 'off'."""
        mode_lower = mode.lower()
        if mode_lower not in ("on", "off"):
            raise DataError("DHW mode must be 'on' or 'off'")
        new_val = 1 if mode_lower == "on" else 0

        path = f"/api/v2/remote/bsbPlantData/{self.config.gateway_id}/dhwMode"
        payload = {"new": new_val}
        self._request("POST", path, json=payload)
        return True

    def set_data_item(self, item_id: str, value: Any, zone: int = 0) -> bool:
        """Set a generic data item via the v2 API."""
        # Read current value first
        current = self.get_system_items([{"id": item_id, "zn": zone}])
        old_val = current.get(item_id, 0)

        path = f"/api/v2/remote/dataItems/{self.config.gateway_id}/set?umsys=si"
        payload = {
            "items": [{"id": item_id, "prevValue": old_val, "value": value, "zone": zone}],
            "features": FEATURES_PAYLOAD,
        }
        self._request("POST", path, json=payload)
        return True

    # ---- Write operations (gas boiler: v2 BSB data items) ----

    def set_data_items(self, changes: dict) -> bool:
        """Write one or more data items (gas boilers).

        ``changes`` maps a data item id to its new value. The API requires the
        current item objects to be echoed back alongside the requested values.
        """
        raw = self.get_home_data(not_essentials=True, real_features=True)
        items = {item["id"]: item for item in raw.get("items") or []}
        request = []
        previous = []
        for item_id, value in changes.items():
            current = items.get(item_id)
            if current is None:
                raise DataError(f"Data item {item_id} is not available")
            request.append({"itemId": item_id, "value": value})
            previous.append(current)
        if not request:
            return True

        path = f"/R2/PlantAdvancedSettings/Save/{self.config.gateway_id}"
        data = self._request(
            "POST",
            path,
            json={
                "features": self._get_features(),
                "requestItems": request,
                "prevDataItems": previous,
            },
        )
        if isinstance(data, dict) and not data.get("ok", True):
            raise DataError(data.get("message") or "Failed to write data items")
        return True

    def set_boiler_temperatures(
        self,
        comfort: Optional[float] = None,
        reduced: Optional[float] = None,
    ) -> bool:
        """Set the zone comfort and/or reduced temperature (gas boilers)."""
        changes = {}
        if comfort is not None:
            changes[self._comfort_item_id] = comfort
        if reduced is not None:
            changes[self._reduced_item_id] = reduced
        if not changes:
            raise DataError("Specify --comfort and/or --reduced")
        return self.set_data_items(changes)

    def set_plant_mode(self, mode: str) -> bool:
        """Set the plant operation mode: summer, winter, heating-only or off."""
        new_mode = PLANT_MODE_MAP.get(mode.lower().replace("_", " ").strip())
        if new_mode is None:
            raise DataError(
                f"Invalid operation mode '{mode}'. Valid: summer, winter, heating-only, off"
            )
        return self.set_data_items({ITEM_PLANT_MODE: new_mode})

    def set_boiler_zone_mode(self, mode: str) -> bool:
        """Set the boiler zone mode: manual or time-program."""
        new_mode = BOILER_ZONE_MODE_MAP.get(mode.lower().replace("_", " ").strip())
        if new_mode is None:
            raise DataError(f"Invalid zone mode '{mode}'. Valid: manual, time-program")
        return self.set_data_items({ITEM_ZONE_MODE: new_mode})

    def set_flow_setpoint(self, value: float) -> bool:
        """Set the central-heating flow setpoint temperature."""
        return self.set_data_items({ITEM_VIRT_FLOW_SETPOINT: value})

    def set_flow_offset(self, value: float) -> bool:
        """Set the central-heating flow temperature offset."""
        return self.set_data_items({ITEM_VIRT_FLOW_OFFSET: value})


def _float_or_none(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ============================================================================
# MQTT Publisher
# ============================================================================

def publish_mqtt(config: Config, data: HeatingData) -> None:
    """Publish heating data to MQTT broker."""
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        print("Warning: paho-mqtt not installed, skipping MQTT", file=sys.stderr)
        return

    client = mqtt.Client()
    if config.mqtt_username:
        client.username_pw_set(config.mqtt_username, config.mqtt_password)
    try:
        client.connect(config.mqtt_host, config.mqtt_port, keepalive=10)
        client.loop_start()
        time.sleep(0.3)
    except Exception as e:
        print(f"MQTT connection failed: {e}", file=sys.stderr)
        return

    prefix = config.mqtt_topic_prefix
    qos = config.mqtt_qos
    retain = config.mqtt_retain

    topics = {
        f"{prefix}/temperature/current": f"{data.current_temperature:.1f}",
        f"{prefix}/temperature/desired": f"{data.desired_temperature:.1f}",
        f"{prefix}/temperature/comfort": f"{data.comfort_temperature:.1f}",
        f"{prefix}/temperature/reduced": f"{data.reduced_temperature:.1f}",
        f"{prefix}/temperature/outside": f"{data.outside_temperature:.1f}",
        f"{prefix}/heating/mode": data.operation_mode,
        f"{prefix}/heating/active": "true" if data.heating_active else "false",
        f"{prefix}/heating/cooling_active": "true" if data.cooling_active else "false",
        f"{prefix}/heatpump/on": "true" if data.heat_pump_on else "false",
        f"{prefix}/dhw/temperature": f"{data.dhw_temperature:.1f}",
        f"{prefix}/dhw/mode": data.dhw_mode,
        f"{prefix}/dhw/enabled": "true" if data.dhw_enabled else "false",
        f"{prefix}/zone_id": data.zone_id,
        f"{prefix}/timestamp": data.timestamp.isoformat(),
    }
    if data.system_pressure is not None:
        topics[f"{prefix}/system/pressure"] = f"{data.system_pressure:.1f}"
    if data.flow_temperature is not None:
        topics[f"{prefix}/system/flow_temperature"] = f"{data.flow_temperature:.1f}"
    if data.dhw_comfort_temp is not None:
        topics[f"{prefix}/dhw/comfort_temp"] = f"{data.dhw_comfort_temp:.1f}"

    # Gas boiler specifics
    if data.is_gas_boiler:
        topics[f"{prefix}/boiler/plant_mode"] = data.plant_mode_text
        topics[f"{prefix}/boiler/zone_mode"] = data.boiler_zone_mode_text
        topics[f"{prefix}/boiler/heat_request"] = "true" if data.heat_request else "false"
        topics[f"{prefix}/boiler/flame_on"] = "true" if data.flame_on else "false"
        topics[f"{prefix}/boiler/holiday"] = "true" if data.holiday else "false"
        if data.ch_flow_setpoint is not None:
            topics[f"{prefix}/boiler/ch_flow_setpoint"] = f"{data.ch_flow_setpoint:.1f}"
        if data.virt_flow_setpoint is not None:
            topics[f"{prefix}/boiler/flow_setpoint"] = f"{data.virt_flow_setpoint:.1f}"
        if data.virt_flow_offset is not None:
            topics[f"{prefix}/boiler/flow_offset"] = f"{data.virt_flow_offset:.1f}"
        if data.gas_heating_month is not None:
            topics[f"{prefix}/boiler/gas_heating_month_kwh"] = f"{data.gas_heating_month:.1f}"
        if data.gas_dhw_month is not None:
            topics[f"{prefix}/boiler/gas_dhw_month_kwh"] = f"{data.gas_dhw_month:.1f}"
        if data.boiler_electricity_month is not None:
            topics[f"{prefix}/boiler/electricity_month_kwh"] = f"{data.boiler_electricity_month:.2f}"

    # Also publish full JSON payload
    topics[f"{prefix}/data"] = json.dumps(data.to_dict())

    for topic, payload in topics.items():
        client.publish(topic, payload, qos=qos, retain=retain)

    client.loop_stop()
    client.disconnect()
    print(f"Published {len(topics)} MQTT topics to {prefix}", file=sys.stderr)


# ============================================================================
# Display
# ============================================================================

def display_status(data: HeatingData) -> None:
    print("=" * 50)
    print("  Elco Heating System Status")
    print("=" * 50)
    print(f"  Retrieved:  {data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  System:     {'Gas boiler' if data.is_gas_boiler else 'Heat pump'}")
    print(f"  Zone:       {data.zone_id}")
    print()

    print("  Temperatures")
    print("  " + "-" * 46)
    if data.current_temperature > 0:
        print(f"  Room Current:   {data.current_temperature:.1f} °C")
    print(f"  Desired:        {data.desired_temperature:.1f} °C")
    print(f"  Comfort Set:    {data.comfort_temperature:.1f} °C")
    print(f"  Reduced Set:    {data.reduced_temperature:.1f} °C")
    if data.cool_comfort_temperature is not None:
        print(f"  Cool Comfort:   {data.cool_comfort_temperature:.1f} °C")
    if data.cool_reduced_temperature is not None:
        print(f"  Cool Reduced:   {data.cool_reduced_temperature:.1f} °C")
    print()

    print("  Outside")
    print("  " + "-" * 46)
    print(f"  Temperature:    {data.outside_temperature:.1f} °C")
    print()

    if data.is_gas_boiler:
        print("  Boiler")
        print("  " + "-" * 46)
        print(f"  Operation Mode: {data.plant_mode_text} ({data.plant_mode})")
        print(f"  Zone Mode:      {data.boiler_zone_mode_text} ({data.boiler_zone_mode})")
        print(f"  Heat Request:   {'Yes' if data.heat_request else 'No'}")
        print(f"  Burner Flame:   {'On' if data.flame_on else 'Off'}")
        print(f"  Holiday:        {'Yes' if data.holiday else 'No'}")
        if data.auto_thermoregulation is not None:
            print(f"  Auto Therm.:    {'On' if data.auto_thermoregulation else 'Off'}")
        if data.ch_flow_setpoint is not None:
            print(f"  CH Flow Set:    {data.ch_flow_setpoint:.1f} °C")
        if data.virt_flow_setpoint is not None:
            print(f"  Flow Setpoint:  {data.virt_flow_setpoint:.1f} °C")
        if data.virt_flow_offset is not None:
            print(f"  Flow Offset:    {data.virt_flow_offset:+.1f}")
        print()

        print("  Consumption (this month)")
        print("  " + "-" * 46)
        if data.gas_heating_month is not None:
            print(f"  Gas Heating:    {data.gas_heating_month:.1f} kWh")
        if data.gas_dhw_month is not None:
            print(f"  Gas Hot Water:  {data.gas_dhw_month:.1f} kWh")
        if data.boiler_electricity_month is not None:
            print(f"  Electricity:    {data.boiler_electricity_month:.2f} kWh")
        print()
    else:
        print("  Heating / Cooling")
        print("  " + "-" * 46)
        print(f"  Mode:           {data.operation_mode} ({data.operation_mode_value})")
        print(f"  Heating Active: {'Yes' if data.heating_active else 'No'}")
        print(f"  Cooling Active: {'Yes' if data.cooling_active else 'No'}")
        print(f"  Heat/Cool Req:  {'Yes' if data.heat_or_cool_request else 'No'}")
        print(f"  Heat Pump:      {'On' if data.heat_pump_on else 'Off'}")
        print()

        print("  Domestic Hot Water")
        print("  " + "-" * 46)
        print(f"  Temperature:    {data.dhw_temperature:.1f} °C")
        if data.dhw_comfort_temp is not None:
            print(f"  Comfort Set:    {data.dhw_comfort_temp:.1f} °C")
        if data.dhw_reduced_temp is not None:
            print(f"  Reduced Set:    {data.dhw_reduced_temp:.1f} °C")
        print(f"  Mode:           {data.dhw_mode}")
        print(f"  Enabled:        {'Yes' if data.dhw_enabled else 'No'}")
        print()

    print("  System")
    print("  " + "-" * 46)
    print(f"  Boiler:         {data.boiler_status}")
    if data.system_pressure is not None:
        print(f"  Pressure:       {data.system_pressure:.1f} bar")
    if data.flow_temperature is not None:
        print(f"  Flow Temp:      {data.flow_temperature:.1f} °C")
    print()


# ============================================================================
# CLI Commands
# ============================================================================

def cmd_status(client: RemoconClient, config: Config, args: argparse.Namespace) -> int:
    """Read and display current status."""
    data = client.get_full_data()
    if args.json:
        print(json.dumps(data.to_dict(), indent=2))
    else:
        display_status(data)

    if config.mqtt_enabled:
        publish_mqtt(config, data)
    return 0


def cmd_set_temp(client: RemoconClient, config: Config, args: argparse.Namespace) -> int:
    """Set zone temperature setpoints."""
    if args.comfort is None and args.reduced is None:
        print("Error: specify --comfort and/or --reduced temperature", file=sys.stderr)
        return 1

    if client.is_gas_boiler():
        client.set_boiler_temperatures(comfort=args.comfort, reduced=args.reduced)
        print(f"Boiler zone {config.zone_id} temperatures updated "
              f"(comfort={args.comfort}, reduced={args.reduced})")
    else:
        client.set_zone_temperatures(
            comfort=args.comfort,
            reduced=args.reduced,
            is_cooling=args.cooling,
        )
        print(f"Zone {config.zone_id} temperatures updated "
              f"(comfort={args.comfort}, reduced={args.reduced}, "
              f"cooling={args.cooling})")
    return 0


def cmd_set_mode(client: RemoconClient, config: Config, args: argparse.Namespace) -> int:
    """Set the operation mode.

    Gas boilers: plant operation mode (summer/winter/heating-only/off).
    Heat pumps: zone mode (protection/automatic/reduction/comfort).
    """
    if client.is_gas_boiler():
        client.set_plant_mode(args.mode)
        print(f"Boiler operation mode set to: {args.mode}")
    else:
        client.set_zone_mode(args.mode, is_cooling=args.cooling)
        print(f"Zone {config.zone_id} mode set to: {args.mode}")
    return 0


def cmd_set_operation_mode(client: RemoconClient, config: Config, args: argparse.Namespace) -> int:
    """Set the plant operation mode (gas boilers)."""
    client.set_plant_mode(args.mode)
    print(f"Operation mode set to: {args.mode}")
    return 0


def cmd_set_zone_mode(client: RemoconClient, config: Config, args: argparse.Namespace) -> int:
    """Set the boiler zone mode (manual/time-program)."""
    client.set_boiler_zone_mode(args.mode)
    print(f"Zone mode set to: {args.mode}")
    return 0


def cmd_set_flow_setpoint(client: RemoconClient, config: Config, args: argparse.Namespace) -> int:
    """Set the central-heating flow setpoint temperature."""
    client.set_flow_setpoint(args.value)
    print(f"Flow setpoint set to: {args.value} °C")
    return 0


def cmd_set_flow_offset(client: RemoconClient, config: Config, args: argparse.Namespace) -> int:
    """Set the central-heating flow temperature offset."""
    client.set_flow_offset(args.value)
    print(f"Flow offset set to: {args.value}")
    return 0


def cmd_set_dhw_temp(client: RemoconClient, config: Config, args: argparse.Namespace) -> int:
    """Set DHW temperature setpoints."""
    if args.comfort is None and args.reduced is None:
        print("Error: specify --comfort and/or --reduced temperature", file=sys.stderr)
        return 1

    client.set_dhw_temperature(comfort=args.comfort, reduced=args.reduced)
    print(f"DHW temperatures updated (comfort={args.comfort}, reduced={args.reduced})")
    return 0


def cmd_set_dhw_mode(client: RemoconClient, config: Config, args: argparse.Namespace) -> int:
    """Set DHW mode (on/off)."""
    client.set_dhw_mode(args.mode)
    print(f"DHW mode set to: {args.mode}")
    return 0


def cmd_raw_get(client: RemoconClient, config: Config, args: argparse.Namespace) -> int:
    """Fetch and display raw data (for debugging/exploration)."""
    raw = client.get_home_data(not_essentials=True, real_features=True)
    print(json.dumps(raw, indent=2))
    return 0


# ============================================================================
# Argument Parser
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="remocon",
        description="Control your Elco heating system via the Remocon-Net cloud API",
    )
    # Global config options
    _add_config_args(parser)

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # status
    p_status = sub.add_parser("status", help="Show current heating system status")
    p_status.add_argument("--json", action="store_true", help="Output as JSON")
    _add_config_args(p_status)

    # set-temp
    p_temp = sub.add_parser("set-temp", help="Set zone temperature setpoints")
    p_temp.add_argument("--comfort", type=float, help="Comfort temperature (°C)")
    p_temp.add_argument("--reduced", type=float, help="Reduced temperature (°C)")
    p_temp.add_argument("--cooling", action="store_true", help="Set cooling temperatures")
    _add_config_args(p_temp)

    # set-mode
    # Gas boilers: plant operation mode. Heat pumps: zone mode.
    p_mode = sub.add_parser("set-mode", help="Set operation mode")
    p_mode.add_argument(
        "mode",
        choices=["protection", "automatic", "reduction", "comfort",
                 "summer", "winter", "heating-only", "off"],
        help="Operation mode (boiler: summer/winter/heating-only/off; "
             "heat pump: protection/automatic/reduction/comfort)",
    )
    p_mode.add_argument("--cooling", action="store_true", help="Set cooling mode")
    _add_config_args(p_mode)

    # set-operation-mode (gas boiler)
    p_op = sub.add_parser("set-operation-mode", help="Set boiler operation mode")
    p_op.add_argument("mode", choices=["summer", "winter", "heating-only", "off"],
                      help="Plant operation mode")
    _add_config_args(p_op)

    # set-zone-mode (gas boiler)
    p_zm = sub.add_parser("set-zone-mode", help="Set boiler zone mode (manual/time-program)")
    p_zm.add_argument("mode", choices=["manual", "time-program"],
                      help="Zone mode")
    _add_config_args(p_zm)

    # set-flow-setpoint (gas boiler)
    p_fs = sub.add_parser("set-flow-setpoint", help="Set central-heating flow setpoint (°C)")
    p_fs.add_argument("value", type=float, help="Flow setpoint temperature (°C)")
    _add_config_args(p_fs)

    # set-flow-offset (gas boiler)
    p_fo = sub.add_parser("set-flow-offset", help="Set central-heating flow temperature offset")
    p_fo.add_argument("value", type=float, help="Flow temperature offset")
    _add_config_args(p_fo)

    # set-dhw-temp
    p_dhw_temp = sub.add_parser("set-dhw-temp", help="Set DHW temperatures")
    p_dhw_temp.add_argument("--comfort", type=float, help="DHW comfort temperature (°C)")
    p_dhw_temp.add_argument("--reduced", type=float, help="DHW reduced temperature (°C)")
    _add_config_args(p_dhw_temp)

    # set-dhw-mode
    p_dhw_mode = sub.add_parser("set-dhw-mode", help="Set DHW mode (on/off)")
    p_dhw_mode.add_argument("mode", choices=["on", "off"], help="DHW mode")
    _add_config_args(p_dhw_mode)

    # raw-get
    p_raw = sub.add_parser("raw-get", help="Fetch raw API response (debug)")
    _add_config_args(p_raw)

    return parser


def _add_config_args(parser: argparse.ArgumentParser) -> None:
    """Add configuration arguments to a parser or subparser.

    Uses argparse.SUPPRESS as default so that args provided on the main
    parser are not overwritten by None from a subparser.
    """
    SUP = argparse.SUPPRESS
    parser.add_argument("--email", type=str, help="Remocon-Net email", default=SUP)
    parser.add_argument("--password", type=str, help="Remocon-Net password", default=SUP)
    parser.add_argument("--gateway", type=str, help="Gateway ID", default=SUP)
    parser.add_argument("--zone", type=str, help="Zone ID (default: 1)", default=SUP)
    parser.add_argument("--config-file", type=str, help="Path to config JSON file", default=SUP)
    parser.add_argument("--mqtt-enabled", action="store_true", dest="mqtt_enabled", default=SUP)
    parser.add_argument("--mqtt-host", type=str, dest="mqtt_host", default=SUP)
    parser.add_argument("--mqtt-port", type=int, dest="mqtt_port", default=SUP)
    parser.add_argument("--mqtt-topic", type=str, dest="mqtt_topic_prefix", default=SUP)
    parser.add_argument("--mqtt-retain", action="store_true", dest="mqtt_retain", default=SUP)


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        config = build_config(args)
        client = RemoconClient(config)

        # Auto-retry once on expired session
        try:
            cmd_func = {
                "status": cmd_status,
                "set-temp": cmd_set_temp,
                "set-mode": cmd_set_mode,
                "set-operation-mode": cmd_set_operation_mode,
                "set-zone-mode": cmd_set_zone_mode,
                "set-flow-setpoint": cmd_set_flow_setpoint,
                "set-flow-offset": cmd_set_flow_offset,
                "set-dhw-temp": cmd_set_dhw_temp,
                "set-dhw-mode": cmd_set_dhw_mode,
                "raw-get": cmd_raw_get,
            }[args.command]
            return cmd_func(client, config, args)
        except SessionExpiredError:
            client.login()
            return cmd_func(client, config, args)

    except ConfigError as e:
        print(f"Config error: {e.message}", file=sys.stderr)
        return e.exit_code
    except AuthError as e:
        print(f"Auth error: {e.message}", file=sys.stderr)
        return e.exit_code
    except NetworkError as e:
        print(f"Network error: {e.message}", file=sys.stderr)
        return e.exit_code
    except DataError as e:
        print(f"Data error: {e.message}", file=sys.stderr)
        return e.exit_code
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
