# Aneo Mobility (Home Assistant integration)

A custom Home Assistant integration for Aneo Mobility EV chargers, providing charger status, price information, and basic control (start/stop charging and cable lock).

## Status / disclaimer

This project is provided as-is and is not affiliated with Aneo Mobility.

**Important:** Most of the code in this repository was AI-generated (with manual review and edits). Please audit it yourself before relying on it for safety- or cost-critical automation.

## Features

- Sensors
  - Raw charger status (mapped to `charging` / `ready` / `stopped`)
  - Current price (NOK/kWh) + attributes for today/tomorrow hourly prices
- Binary sensors
  - Charging, car connected, cable locked
- Switches
  - Charging control (start/stop)
  - Cable lock (lock/unlock)

## Installation

### Option A: HACS (Custom repository)
1. HACS → Integrations → 3-dots menu → “Custom repositories”
2. Add this repository URL, type “Integration”
3. Install
4. Restart Home Assistant

### Option B: Manual
1. Copy the `aneo_mobility` folder into:
   - `<config>/custom_components/aneo_mobility/`
2. Restart Home Assistant

## Configuration

1. Settings → Devices & services → Add integration
2. Search for “Aneo Mobility”
3. Enter:
   - Base API URL (default should work)
   - Email address
   - Password

### Options

You can adjust update intervals in the integration options:
- Charger state refresh interval (minutes)
- Price data refresh interval (minutes)

## Security notes (read before filing issues)

- This integration stores OAuth-like tokens (access token + refresh token) in the Home Assistant config entry data.
- Home Assistant persists config entry data under its internal storage (commonly in the `.storage/` directory).
- Never publish your Home Assistant `.storage/` directory, backups, or config entry exports, as they may contain your tokens.

If you open GitHub issues, please sanitize logs before posting.

## Development / contribution

PRs are welcome. If you add logs, avoid printing:
- Email/username
- Subscription IDs
- Charger IDs
- Full request URLs that embed identifiers
- Full API error bodies (they may contain identifying info)
