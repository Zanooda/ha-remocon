"""API client for the Elco Remocon-Net cloud service."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote

import requests

from .const import (
    ITEM_AUTOMATIC_THERMOREGULATION,
    ITEM_CH_FLOW_SETPOINT,
    ITEM_CH_FLOW_TEMP,
    ITEM_DHW_MODE,
    ITEM_DHW_STORAGE_TEMP,
    ITEM_DHW_TEMP,
    ITEM_DHW_TIMEPROG_COMFORT_TEMP,
    ITEM_DHW_TIMEPROG_ECONOMY_TEMP,
    DHW_ITEM_DISABLED,
    ITEM_HEATING_CIRCUIT_PRESSURE,
    ITEM_HEATING_FLOW_TEMP,
    ITEM_HOLIDAY,
    ITEM_IS_FLAME_ON,
    ITEM_OUTSIDE_TEMP,
    ITEM_PLANT_MODE,
    ITEM_VIRT_COMFORT_TEMP,
    ITEM_VIRT_FLOW_OFFSET,
    ITEM_VIRT_FLOW_SETPOINT,
    ITEM_VIRT_REDUCED_TEMP,
    ITEM_ZONE_COMFORT_TEMP,
    ITEM_ZONE_DESIRED_TEMP,
    ITEM_ZONE_ECONOMY_TEMP,
    ITEM_ZONE_HEAT_REQUEST,
    ITEM_ZONE_MEASURED_TEMP,
    ITEM_ZONE_MODE,
    MODE_AUTOMATIC,
)

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.remocon-net.remotethermo.com"

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


class RemoconApiError(Exception):
    """Base exception for API errors."""


class RemoconAuthError(RemoconApiError):
    """Authentication failed."""


class RemoconConnectionError(RemoconApiError):
    """Connection error."""


class RemoconDataError(RemoconApiError):
    """Data error."""


@dataclass
class RemoconData:
    """All data from the heating system."""

    # Zone
    comfort_temp: float = 0.0
    comfort_temp_min: float = 5.0
    comfort_temp_max: float = 35.0
    comfort_temp_step: float = 0.5
    reduced_temp: float = 0.0
    desired_temp: float = 0.0
    room_temp: float = 0.0
    zone_mode: int = MODE_AUTOMATIC
    zone_mode_texts: list[str] = field(default_factory=list)
    heating_active: bool = False
    cooling_active: bool = False
    heat_or_cool_request: bool = False
    # Plant
    outside_temp: float = 0.0
    dhw_temp: float = 0.0
    dhw_comfort_temp: float = 0.0
    dhw_reduced_temp: float = 0.0
    dhw_temp_setpoint: Optional[float] = None
    dhw_mode: int = 0
    dhw_enabled: bool = False
    has_dhw: bool = False
    heat_pump_on: bool = False
    flame_sensor: bool = False
    # System (from v2 API)
    system_pressure: Optional[float] = None
    flow_temperature: Optional[float] = None
    # Gas boiler (v2 BSB data items)
    is_gas_boiler: bool = False
    plant_mode: Optional[int] = None
    boiler_zone_mode: Optional[int] = None
    auto_thermoregulation: Optional[bool] = None
    ch_flow_setpoint: Optional[float] = None
    heat_request: bool = False
    holiday: bool = False
    gas_heating_month: Optional[float] = None
    gas_dhw_month: Optional[float] = None
    boiler_electricity_month: Optional[float] = None
    items: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Meta
    has_room_sensor: bool = False

    def item_value(self, item_id: str) -> Optional[float]:
        """Return the current value of a raw data item, if present."""
        item = self.items.get(item_id)
        if item is None:
            return None
        return item.get("value")

    def item_meta(self, item_id: str) -> dict[str, Any]:
        """Return the raw data item (min/max/step/unit), or an empty dict."""
        return self.items.get(item_id) or {}


class RemoconClient:
    """Synchronous API client for Elco Remocon-Net."""

    def __init__(self, email: str, password: str, gateway_id: str, zone: str = "1") -> None:
        self._email = email
        self._password = password
        self._gateway_id = gateway_id
        self._zone = zone
        self._session: Optional[requests.Session] = None
        self._features: Optional[dict[str, Any]] = None
        self._features_dirty = False
        self._features_resolved = False
        self._system_type: Optional[int] = None
        self._is_gas_boiler: Optional[bool] = None
        self._comfort_item_id: str = ITEM_VIRT_COMFORT_TEMP
        self._reduced_item_id: str = ITEM_VIRT_REDUCED_TEMP

    def login(self) -> None:
        """Authenticate and store session cookie."""
        s = requests.Session()
        url = f"{BASE_URL}/R2/Account/Login?returnUrl=HTTP/2"
        payload = (
            f"Email={quote(self._email, safe='')}"
            f"&Password={quote(self._password, safe='')}"
            f"&RememberMe=false"
        )
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": "browserUtcOffset=-120",
        }
        try:
            resp = s.post(url, headers=headers, data=payload, timeout=15)
        except requests.RequestException as err:
            raise RemoconConnectionError(str(err)) from err

        if resp.status_code in (401, 403):
            raise RemoconAuthError("Invalid credentials")
        resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError as err:
            raise RemoconAuthError("Could not parse login response") from err

        if not data.get("ok"):
            raise RemoconAuthError(data.get("message", "Login failed"))

        self._session = s

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self.login()
        return self._session  # type: ignore[return-value]

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        s = self._get_session()
        url = f"{BASE_URL}{path}"
        kwargs.setdefault("timeout", 15)
        try:
            resp = s.request(method, url, **kwargs)
            if resp.status_code in (401, 403):
                raise RemoconAuthError("Session expired")
            resp.raise_for_status()
        except requests.RequestException as err:
            err_msg = str(err)
            if getattr(err, "response", None) is not None:
                err_msg += f" - Response: {err.response.text}"
            _LOGGER.error("API Request failed: %s", err_msg)
            raise RemoconConnectionError(err_msg) from err
        
        try:
            return resp.json()
        except ValueError as err:
            _LOGGER.error("Invalid JSON response from API: %s", resp.text)
            raise RemoconDataError("Could not parse API response") from err

    def _get_features(self) -> dict[str, Any]:
        """Fetch the plant's real feature set (cached).

        The features payload is echoed back to the API and selects which data
        items the plant reports; sending a generic payload makes the server
        return the wrong item set for virtual-zone / boiler systems.
        """
        if self._features is not None:
            return self._features
        try:
            data = self._request(
                "GET", f"/R2/Plant/Features/{self._gateway_id}?eagerMode=false"
            )
            payload = data.get("data") or {}
            features = dict(payload.get("features") or {})
            plant = payload.get("plant") or {}
            if plant.get("gatewayId"):
                features["gatewayId"] = plant["gatewayId"]
            self._system_type = plant.get("systemType")
            self._features = features or dict(FEATURES_PAYLOAD)
            self._features_resolved = bool(features)
        except RemoconApiError as err:
            _LOGGER.debug("Could not fetch plant features, using defaults: %s", err)
            self._features = dict(FEATURES_PAYLOAD)
            self._features_resolved = False
        return self._features

    def _merge_features(self, features: Any) -> bool:
        """Merge non-null feature flags from an API response into the cache.

        The API resolves flags the /Features endpoint leaves null (e.g. the DHW
        flags) and returns the resolved set with every GetData response. Those
        flags select the reported data items, so we must adopt them (and refetch
        once) to see e.g. the DHW items.
        """
        if not isinstance(features, dict):
            return False
        if self._features is None:
            self._features = dict(features)
            return True
        changed = False
        for key, value in features.items():
            if value is None:
                continue
            if self._features.get(key) != value:
                self._features[key] = value
                changed = True
        return changed

    def _get_raw(self, *, not_essentials: bool = False, real_features: bool = False) -> dict:
        path = f"/R2/PlantHome/GetData/{self._gateway_id}?umsys=si"
        payload = {
            "useCache": True,
            "zone": int(self._zone),
            "filter": {
                "notEssentials": not_essentials,
                "plant": True,
                "zone": True,
                "dhw": True,
            },
            "features": self._get_features() if real_features else FEATURES_PAYLOAD,
        }
        data = self._request("POST", path, json=payload)
        if not data:
            raise RemoconDataError("Empty data received from API")
        if isinstance(data, dict) and not data.get("ok", True):
            _LOGGER.error("API returned error: %s", data)
            raise RemoconDataError(data.get("message", "API returned error"))
        result = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(result, dict) and self._merge_features(result.get("features")):
            self._features_dirty = True
        return result

    def _get_system_items(self, item_ids: list[dict]) -> dict[str, Any]:
        path = f"/api/v2/remote/dataItems/{self._gateway_id}/get?umsys=si"
        payload = {
            "useCache": False,
            "items": item_ids,
            "features": FEATURES_PAYLOAD,
            "culture": "de",
        }
        data = self._request("POST", path, json=payload)
        return {item["id"]: item.get("value") for item in data.get("items", [])} if isinstance(data, dict) else {}

    def get_data(self) -> RemoconData:
        """Fetch all data and return a RemoconData object."""
        if self._is_gas_boiler is None:
            features = self._get_features()
            if self._features_resolved:
                # The /Features endpoint resolves whether this is a boiler.
                self._is_gas_boiler = bool(features.get("hasBoiler")) and not bool(
                    features.get("hpSys")
                )
            else:
                probe = self._get_raw()
                if "plantData" in probe or "zoneData" in probe:
                    self._is_gas_boiler = False
                    return self._parse_heat_pump(probe)
                self._is_gas_boiler = bool(probe.get("items"))

        if not self._is_gas_boiler:
            return self._parse_heat_pump(self._get_raw())

        # Boilers report a flat item list and need the real feature set. The
        # first response resolves feature flags the /Features endpoint leaves
        # null (e.g. DHW) and which gate additional items, so refetch once with
        # the resolved set to get a complete item list on the first poll.
        self._features_dirty = False
        raw = self._get_raw(not_essentials=True, real_features=True)
        if self._features_dirty:
            self._features_dirty = False
            raw = self._get_raw(not_essentials=True, real_features=True)
        if not isinstance(raw, dict):
            raise RemoconDataError(f"Unexpected data format from API: {type(raw)}")

        data = self._parse_gas_boiler(raw)
        try:
            self._apply_metering(data)
        except RemoconApiError as err:
            _LOGGER.debug("Could not fetch metering data: %s", err)
        return data

    def _parse_heat_pump(self, raw: dict) -> RemoconData:
        """Parse a heat-pump (plantData/zoneData) response."""
        plant = raw.get("plantData") or {}
        zone = raw.get("zoneData") or {}

        sys_items: dict[str, Any] = {}
        try:
            sys_items = self._get_system_items([
                {"id": "HeatingCircuitPressure", "zn": 0},
                {"id": "ChFlowTemp", "zn": 0},
            ])
        except Exception as err:
            _LOGGER.debug("Could not fetch system items from v2 API: %s", err)

        ch_comfort = zone.get("chComfortTemp") or {}
        ch_reduced = zone.get("chReducedTemp") or {}
        mode_info = zone.get("mode") or {}

        pressure = sys_items.get("HeatingCircuitPressure")
        flow = sys_items.get("ChFlowTemp")

        dhw_comfort = plant.get("dhwComfortTemp") or {}
        dhw_reduced = plant.get("dhwReducedTemp") or {}
        dhw_mode_info = plant.get("dhwMode") or {}

        return RemoconData(
            comfort_temp=float(ch_comfort.get("value", 0)),
            comfort_temp_min=float(ch_comfort.get("min", 5)),
            comfort_temp_max=float(ch_comfort.get("max", 35)),
            comfort_temp_step=float(ch_comfort.get("step", 0.5)),
            reduced_temp=float(ch_reduced.get("value", 0)),
            desired_temp=float(zone.get("desiredRoomTemp", 0)),
            room_temp=float(zone.get("roomTemp", 0)),
            zone_mode=mode_info.get("value", MODE_AUTOMATIC),
            zone_mode_texts=mode_info.get("allowedOptionTexts", []),
            heating_active=bool(zone.get("isHeatingActive", 0)),
            cooling_active=bool(zone.get("isCoolingActive", 0)),
            heat_or_cool_request=bool(zone.get("heatOrCoolRequest", 0)),
            outside_temp=float(plant.get("outsideTemp", 0)),
            dhw_temp=float(plant.get("dhwStorageTemp", 0)),
            dhw_comfort_temp=float(dhw_comfort.get("value", 0)),
            dhw_reduced_temp=float(dhw_reduced.get("value", 0)),
            dhw_mode=dhw_mode_info.get("value", 0),
            dhw_enabled=bool(plant.get("dhwEnabled", 0)),
            has_dhw=bool(plant.get("dhwEnabled", 0)),
            heat_pump_on=bool(plant.get("heatPumpOn", 0)),
            flame_sensor=bool(plant.get("flameSensor", 0)),
            system_pressure=float(pressure) if pressure is not None else None,
            flow_temperature=float(flow) if flow is not None else None,
            has_room_sensor=bool(zone.get("hasRoomSensor", 0)),
        )

    def _parse_gas_boiler(self, raw: dict) -> RemoconData:
        """Parse a gas-boiler (flat items[]) response."""
        data = RemoconData(is_gas_boiler=True)
        items = raw.get("items") or []
        data.items = {item["id"]: item for item in items if item.get("id")}

        def value(item_id: str) -> Optional[float]:
            return data.item_value(item_id)

        def meta(item_id: str) -> dict[str, Any]:
            return data.item_meta(item_id)

        # Zone comfort / reduced setpoints (virtual zones use Virt* items)
        comfort = meta(ITEM_VIRT_COMFORT_TEMP) or meta(ITEM_ZONE_COMFORT_TEMP)
        reduced = meta(ITEM_VIRT_REDUCED_TEMP) or meta(ITEM_ZONE_ECONOMY_TEMP)
        if comfort:
            self._comfort_item_id = comfort["id"]
            data.comfort_temp = float(comfort.get("value", 0))
            data.comfort_temp_min = float(comfort.get("min", 5))
            data.comfort_temp_max = float(comfort.get("max", 35))
            data.comfort_temp_step = float(comfort.get("step", 0.5)) or 0.5
        if reduced:
            self._reduced_item_id = reduced["id"]
            data.reduced_temp = float(reduced.get("value", 0))

        outside = value(ITEM_OUTSIDE_TEMP)
        if outside is not None:
            data.outside_temp = float(outside)
        desired = value(ITEM_ZONE_DESIRED_TEMP)
        if desired is not None:
            data.desired_temp = float(desired)
        measured = value(ITEM_ZONE_MEASURED_TEMP)
        if measured is not None:
            data.room_temp = float(measured)
            data.has_room_sensor = float(measured) > 0

        plant_mode = value(ITEM_PLANT_MODE)
        if plant_mode is not None:
            data.plant_mode = int(plant_mode)
        zone_mode = value(ITEM_ZONE_MODE)
        if zone_mode is not None:
            data.boiler_zone_mode = int(zone_mode)
        auto_thermo = value(ITEM_AUTOMATIC_THERMOREGULATION)
        if auto_thermo is not None:
            data.auto_thermoregulation = bool(auto_thermo)
        flow_setpoint = value(ITEM_CH_FLOW_SETPOINT)
        if flow_setpoint is not None:
            data.ch_flow_setpoint = float(flow_setpoint)
        heat_request = value(ITEM_ZONE_HEAT_REQUEST)
        if heat_request is not None:
            data.heat_request = bool(heat_request)
            data.heating_active = bool(heat_request)
        flame = value(ITEM_IS_FLAME_ON)
        if flame is not None:
            data.flame_sensor = bool(flame)
        holiday = value(ITEM_HOLIDAY)
        if holiday is not None:
            data.holiday = bool(holiday)

        for flow_id in (ITEM_CH_FLOW_TEMP, ITEM_HEATING_FLOW_TEMP):
            flow = value(flow_id)
            if flow is not None:
                data.flow_temperature = float(flow)
                break
        pressure = value(ITEM_HEATING_CIRCUIT_PRESSURE)
        if pressure is not None:
            data.system_pressure = float(pressure)

        # Domestic hot water (only present when the plant exposes a DHW circuit)
        dhw_mode = value(ITEM_DHW_MODE)
        if dhw_mode is not None:
            data.has_dhw = True
            data.dhw_mode = int(dhw_mode)
            data.dhw_enabled = int(dhw_mode) != DHW_ITEM_DISABLED
        dhw_storage = value(ITEM_DHW_STORAGE_TEMP)
        if dhw_storage is not None:
            data.dhw_temp = float(dhw_storage)
        dhw_setpoint = value(ITEM_DHW_TEMP)
        if dhw_setpoint is not None:
            data.dhw_temp_setpoint = float(dhw_setpoint)
        dhw_comfort = value(ITEM_DHW_TIMEPROG_COMFORT_TEMP)
        if dhw_comfort is not None:
            data.dhw_comfort_temp = float(dhw_comfort)
        dhw_reduced = value(ITEM_DHW_TIMEPROG_ECONOMY_TEMP)
        if dhw_reduced is not None:
            data.dhw_reduced_temp = float(dhw_reduced)
        if any(i in data.items for i in (ITEM_DHW_TEMP, ITEM_DHW_STORAGE_TEMP)):
            data.has_dhw = True

        return data

    def _apply_metering(self, data: RemoconData) -> None:
        """Populate gas/electricity consumption (boilers only)."""
        metering = self._get_metering()
        data.gas_heating_month = metering.get("heating")
        data.gas_dhw_month = metering.get("dhw")
        data.boiler_electricity_month = metering.get("electricity")

    def _get_metering(self) -> dict[str, float]:
        """Return current-month consumption in kWh from the metering API."""
        result: dict[str, float] = {}
        payload = self._request(
            "POST", f"/R2/PlantMetering/GetData/{self._gateway_id}", json={}, timeout=30
        )
        data = payload.get("data") or {}
        as_kwh = data.get("asKwh") or {}
        for row in as_kwh.get("donutData") or []:
            if row.get("tab") != "ConsumedGas" or row.get("period") != "CurrentMonth":
                continue
            series = str(row.get("series", "")).lower()
            result[series] = float(row.get("value") or 0)
        for row in as_kwh.get("boilerElectricity") or []:
            if row.get("period") == "CurrentMonth":
                result["electricity"] = float(row.get("value") or 0)
        return result

    def set_zone_temperatures(
        self, comfort: float | None = None, reduced: float | None = None
    ) -> None:
        """Set comfort and/or reduced temperature."""
        raw = self._get_raw()
        if not isinstance(raw, dict):
            raw = {}
        zone = raw.get("zoneData") or {}
        ch_comf = zone.get("chComfortTemp") or {}
        ch_red = zone.get("chReducedTemp") or {}
        old_comf = float(ch_comf.get("value", 0))
        old_econ = float(ch_red.get("value", 0))

        new_comf = comfort if comfort is not None else old_comf
        new_econ = reduced if reduced is not None else old_econ

        path = (
            f"/api/v2/remote/bsbZones/{self._gateway_id}"
            f"/{self._zone}/temperatures?isCooling=false"
        )
        self._request("POST", path, json={
            "new": {"comf": new_comf, "econ": new_econ},
            "old": {"comf": old_comf, "econ": old_econ},
        })

    def set_zone_mode(self, mode: int) -> None:
        """Set zone operation mode."""
        raw = self._get_raw()
        if not isinstance(raw, dict):
            raw = {}
        zone = raw.get("zoneData") or {}
        mode_info = zone.get("mode") or {}
        old_mode = mode_info.get("value", MODE_AUTOMATIC)

        path = (
            f"/api/v2/remote/bsbZones/{self._gateway_id}"
            f"/{self._zone}/mode?isCooling=false"
        )
        self._request("POST", path, json={"new": mode, "old": old_mode})

    def set_dhw_temperature(
        self, comfort: float | None = None, reduced: float | None = None
    ) -> None:
        """Set DHW temperatures."""
        raw = self._get_raw()
        if not isinstance(raw, dict):
            raw = {}
        plant = raw.get("plantData") or {}
        dhw_comf = plant.get("dhwComfortTemp") or {}
        dhw_red = plant.get("dhwReducedTemp") or {}
        old_comf = float(dhw_comf.get("value", 0))
        old_econ = float(dhw_red.get("value", 0))

        new_comf = comfort if comfort is not None else old_comf
        new_econ = reduced if reduced is not None else old_econ

        path = f"/api/v2/remote/bsbPlantData/{self._gateway_id}/dhwTemp"
        self._request("POST", path, json={
            "new": {"comf": new_comf, "econ": new_econ},
            "old": {"comf": old_comf, "econ": old_econ},
        })

    def set_dhw_mode(self, mode: int) -> None:
        """Set DHW mode: 0=off, 1=on."""
        path = f"/api/v2/remote/bsbPlantData/{self._gateway_id}/dhwMode"
        self._request("POST", path, json={"new": mode})

    # ---- Gas boiler control (v2 BSB data items) ----

    def set_data_items(self, changes: dict[str, float]) -> None:
        """Write one or more data items.

        ``changes`` maps a data item id to its new value. The API requires the
        current item objects to be echoed back alongside the requested values.
        """
        # Ensure the resolved feature set (e.g. DHW flags) is used so the item
        # set and the echoed features are complete.
        self._features_dirty = False
        raw = self._get_raw(not_essentials=True, real_features=True)
        if self._features_dirty:
            self._features_dirty = False
            raw = self._get_raw(not_essentials=True, real_features=True)
        items = {item["id"]: item for item in raw.get("items") or []}
        request: list[dict[str, Any]] = []
        previous: list[dict[str, Any]] = []
        for item_id, value in changes.items():
            current = items.get(item_id)
            if current is None:
                raise RemoconDataError(f"Data item {item_id} is not available")
            request.append({"itemId": item_id, "value": value})
            previous.append(current)
        if not request:
            return
        self._request(
            "POST",
            f"/R2/PlantAdvancedSettings/Save/{self._gateway_id}",
            json={
                "features": self._get_features(),
                "requestItems": request,
                "prevDataItems": previous,
            },
        )

    def set_boiler_comfort_temperature(self, temperature: float) -> None:
        """Set the zone comfort (day) temperature."""
        self.set_data_items({self._comfort_item_id: temperature})

    def set_boiler_reduced_temperature(self, temperature: float) -> None:
        """Set the zone reduced (night) temperature."""
        self.set_data_items({self._reduced_item_id: temperature})

    def set_plant_mode(self, mode: int) -> None:
        """Set the plant operation mode (summer/winter/heating only/off)."""
        self.set_data_items({ITEM_PLANT_MODE: mode})

    def set_boiler_zone_mode(self, mode: int) -> None:
        """Set the boiler zone mode (manual / time program)."""
        self.set_data_items({ITEM_ZONE_MODE: mode})

    def set_flow_setpoint(self, value: float) -> None:
        """Set the central-heating flow setpoint temperature."""
        self.set_data_items({ITEM_VIRT_FLOW_SETPOINT: value})

    def set_flow_offset(self, value: float) -> None:
        """Set the central-heating flow temperature offset."""
        self.set_data_items({ITEM_VIRT_FLOW_OFFSET: value})

    def set_dhw_setpoint(self, temperature: float) -> None:
        """Set the domestic hot water setpoint (gas boilers)."""
        self.set_data_items({ITEM_DHW_TEMP: temperature})

    def set_boiler_dhw_mode(self, mode: int) -> None:
        """Set the domestic hot water mode (0 disabled/1 time based/2 always)."""
        self.set_data_items({ITEM_DHW_MODE: mode})

    def reauth(self) -> None:
        """Force re-authentication."""
        self._session = None
        self.login()
