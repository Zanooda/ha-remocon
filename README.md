# ha-remocon

**Unofficial Home Assistant integration for Elco heating systems via the Remocon-Net cloud service.**

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Zanooda&repository=ha-remocon&category=integration)

Control and monitor your Elco heating system (heat pump e.g. Aerotop SPK, or gas boiler) through the Remocon-Net cloud API — directly in Home Assistant, no MQTT or AppDaemon needed.

> **Disclaimer:** This is an unofficial community project. It is not endorsed by or affiliated with Elco or the Ariston Thermo Group.

## Features

**Heat pumps**
- **Climate entity** — Set target temperature, switch operation mode (Auto / Heat / Off), presets (Comfort / Reduced)
- **Sensors** — Outside temperature, flow temperature, target temperature, system pressure
- **Binary sensors** — Heating active, cooling active, heat pump running

**Gas boilers** (virtual-zone boilers, e.g. residential gas boilers)
- **Climate entity** — Set the room setpoint; switch operation mode (Off / Heat / Auto)
- **Select entities** — Operation mode (Summer / Winter / Heating only / Off), zone mode (Manual / Time program) and hot water mode (Disabled / Time based / Always active)
- **Number entities** — Central-heating flow setpoint, flow offset, reduced temperature, hot water setpoint
- **Sensors** — Outside temperature, desired/reduced temperature, flow setpoint, hot water temperature, gas and electricity consumption (current month)
- **Binary sensors** — Burner flame, heat request, hot water active

Hot water entities are only created when the boiler exposes a DHW circuit.

**Common**
- **Config flow** — Easy setup directly in the Home Assistant UI
- **CLI tool** — Standalone `remocon.py` for testing and debugging from the terminal

## Requirements

- Elco heat pump or gas boiler with a Remocon-Net gateway (connected to the internet)
- Remocon-Net account ([remocon-net.remotethermo.com](https://www.remocon-net.remotethermo.com))
- Home Assistant >= 2024.1.0
- [HACS](https://hacs.xyz/) installed

## Installation

### Via HACS (recommended)

1. Open HACS in Home Assistant
2. **≡ Menu** → **Custom Repositories**
3. Add:
   - **URL:** `https://github.com/Zanooda/ha-remocon`
   - **Category:** Integration
4. Search for **"Remocon-Net"** in HACS and install
5. Restart Home Assistant

### Manual

```bash
cd /path/to/homeassistant/config/custom_components/
git clone https://github.com/Zanooda/ha-remocon.git elco_remocon_temp
cp -r elco_remocon_temp/custom_components/elco_remocon ./
rm -rf elco_remocon_temp
```

Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **"Remocon-Net"**
3. Enter your credentials:
   - **Email:** Your Remocon-Net login email
   - **Password:** Your Remocon-Net login password
   - **Gateway ID:** Your system's gateway ID (see below)
   - **Zone:** Heating zone (default: 1)

### Finding your Gateway ID

1. Log in at [remocon-net.remotethermo.com](https://www.remocon-net.remotethermo.com)
2. The gateway ID is shown in the URL, e.g. `A1B2C3D4E5F6` in:
   ```
   https://www.remocon-net.remotethermo.com/R2/Plant/Index/A1B2C3D4E5F6
   ```

## Entities

After setup, the following entities are created (the exact set depends on the
system — heat pumps expose the heat-pump entities, gas boilers the boiler ones):

### Heat pumps

| Entity | Type | Description |
|--------|------|-------------|
| `climate.remocon_net_heat_pump` | Climate | Temperature control, mode, presets |
| `sensor.outside_temperature` | Sensor | Outside temperature |
| `sensor.desired_temperature` | Sensor | Current target temperature |
| `sensor.reduced_temperature` | Sensor | Reduced setpoint temperature |
| `sensor.flow_temperature` | Sensor | Flow temperature |
| `sensor.system_pressure` | Sensor | System pressure (bar) |
| `binary_sensor.heating_active` | Binary | Heating is active |
| `binary_sensor.cooling_active` | Binary | Cooling is active |
| `binary_sensor.heat_pump_on` | Binary | Heat pump is running |

### Gas boilers

| Entity | Type | Description |
|--------|------|-------------|
| `climate.remocon_net_boiler` | Climate | Room setpoint and coarse mode (Off / Heat / Auto) |
| `select.operation_mode` | Select | Operation mode (Summer / Winter / Heating only / Off) |
| `select.zone_mode` | Select | Zone mode (Manual / Time program) |
| `select.dhw_mode` | Select | Hot water mode (Disabled / Time based / Always active) — only with a DHW circuit |
| `number.flow_setpoint` | Number | Central-heating flow setpoint temperature |
| `number.flow_offset` | Number | Central-heating flow temperature offset |
| `number.reduced_temperature` | Number | Reduced (night) setpoint temperature |
| `number.dhw_temperature` | Number | Hot water setpoint — only with a DHW circuit |
| `sensor.outside_temperature` | Sensor | Outside temperature |
| `sensor.desired_temperature` | Sensor | Desired room temperature |
| `sensor.reduced_temperature` | Sensor | Reduced setpoint temperature |
| `sensor.ch_flow_setpoint` | Sensor | Flow setpoint temperature |
| `sensor.dhw_temperature` | Sensor | Measured hot water temperature — only with a DHW circuit |
| `sensor.gas_heating_month` | Sensor | Gas used for heating this month (kWh) |
| `sensor.gas_dhw_month` | Sensor | Gas used for hot water this month (kWh) |
| `sensor.boiler_electricity_month` | Sensor | Electricity used this month (kWh) |
| `binary_sensor.flame_on` | Binary | Burner flame is lit |
| `binary_sensor.heat_request` | Binary | Zone is requesting heat |
| `binary_sensor.dhw_enabled` | Binary | Hot water is active — only with a DHW circuit |

### Climate entity

The climate entity supports:

- **Heat pumps:** modes `Heat` (Comfort), `Auto` (time program), `Off` (frost protection); presets `Comfort`, `Reduced`
- **Gas boilers:** modes `Heat` (heating only), `Auto` (winter), `Off`; the full four-way operation mode is on the `select.operation_mode` entity
- **Temperature:** Adjustable within the range reported by the system

## CLI Tool

A standalone CLI tool is included for testing and debugging. It auto-detects
whether your system is a heat pump or a gas boiler and picks the matching
protocol.

```bash
pip install -r requirements.txt

# Create config
cp config.example.json config.json
# Edit config.json with your email, password and gateway ID

# Check status (auto-detects heat pump / gas boiler)
python3 remocon.py --config-file config.json status

# JSON output (for scripting)
python3 remocon.py --config-file config.json status --json

# Set room / zone temperatures (both systems)
python3 remocon.py --config-file config.json set-temp --comfort 22.0 --reduced 18.0

# Raw API response (debug)
python3 remocon.py --config-file config.json raw-get
```

**Heat pumps** — `set-mode` takes `protection`, `automatic`, `reduction`, `comfort`:

```bash
python3 remocon.py --config-file config.json set-mode comfort
python3 remocon.py --config-file config.json set-dhw-temp --comfort 48 --reduced 40
python3 remocon.py --config-file config.json set-dhw-mode on
```

**Gas boilers** — `set-mode` takes `summer`, `winter`, `heating-only`, `off`; the
boiler-specific commands are:

```bash
# Operation mode (summer / winter / heating-only / off)
python3 remocon.py --config-file config.json set-operation-mode winter
python3 remocon.py --config-file config.json set-mode winter        # same, auto-detected

# Zone mode (manual / time-program)
python3 remocon.py --config-file config.json set-zone-mode manual

# Central-heating flow setpoint and offset
python3 remocon.py --config-file config.json set-flow-setpoint 60
python3 remocon.py --config-file config.json set-flow-offset 5

# Hot water (boilers with a DHW circuit)
python3 remocon.py --config-file config.json set-dhw-temp --comfort 60
python3 remocon.py --config-file config.json set-dhw-mode always-active   # disabled|time-based|always-active
```

### MQTT

With `--mqtt-enabled`, `status` also publishes the data (including
`…/boiler/gas_heating_month_kwh`, `…/boiler/flame_on`, `…/boiler/plant_mode`
for gas boilers) to the configured broker.

## Known limitations

- **Cloud-dependent:** Control goes through the Remocon-Net cloud. No control possible during internet outages.
- **Polling:** Data is fetched every 2 minutes (no real-time streaming).
- **No room sensor:** If no room thermostat is connected, `current_temperature` shows the target value (heat pumps) or is unknown (boilers, which report no measured room temperature).
- **DHW:** Hot water setpoint and mode are controllable where the system exposes a DHW circuit (heat pumps via the BSB API, boilers via data items). Systems without a DHW circuit get no hot water entities.
- **Gas boilers:** Only virtual-zone boilers exposing the v2 data-item model are supported. Heating/cooling curves, holiday programmes and weekly time programmes are not yet exposed.

## Technical details

The integration uses the same API as the Elco Remocon-Net web app:

- **Login:** Cookie-based authentication via `/R2/Account/Login`
- **Data:** R2 Web API (`/R2/PlantHome/GetData/`) + v2 REST API (`/api/v2/remote/dataItems/`)
- **Features:** `/R2/Plant/Features/{gateway}` — the real feature set is sent with every read/write request; it selects which data items the plant reports. The API resolves flags this endpoint leaves null (e.g. the DHW flags) and returns them with each `GetData` response; the integration adopts those and refetches once so e.g. DHW entities appear on the first poll.
- **Control (heat pumps):** v2 REST API (`/api/v2/remote/bsbZones/`, `/api/v2/remote/bsbPlantData/`)
- **Control (gas boilers):** v2 BSB data items via `/R2/PlantAdvancedSettings/Save/{gateway}`
- **Consumption:** `/R2/PlantMetering/GetData/{gateway}` (gas / electricity, current month)
- **Platform:** remotethermo.com (Ariston Thermo Group)

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

MIT
