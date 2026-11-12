# solar-dash for Home Assistant

A Home Assistant custom integration for [solar-dash](https://github.com/anicoll/solar-dash),
a self-hosted dashboard for a home solar and battery system (Sungrow inverter over
Modbus, optional iSolarCloud, GloBird, TeslaMate and Amber prices).

It **polls solar-dash's HTTP API** with a read-only API token, so no MQTT broker is needed.
It is read-only: it never sends a command to solar-dash or the inverter.

## Install with HACS

1. In Home Assistant open **HACS**, then the three-dot menu, then **Custom repositories**.
2. Add `https://github.com/anicoll/solar-dash-ha` with category **Integration**.
3. Find **solar-dash** in HACS, press **Download**, then restart Home Assistant.
4. Go to **Settings, Devices & services, Add integration** and pick **solar-dash**.

Manual install: copy `custom_components/solar_dash` into your Home Assistant
`config/custom_components/` folder and restart.

## Create the API token in solar-dash

Add an `api_token` to the `[server]` section of solar-dash's config and restart it:

```toml
[server]
api_token = "<output of: openssl rand -hex 32>"
```

The token must be at least 32 characters. solar-dash accepts it as
`Authorization: Bearer <token>` on read (GET) requests under `/api/`. It cannot change
anything and cannot download the database backup.

## Set up

Enter solar-dash's address (for example `http://192.168.1.20:8080`) and the token. The
integration checks them with `GET /api/capabilities`. If the token is changed later,
Home Assistant asks you to re-enter it (reauthentication).

**Options:** the live update interval (default 15 seconds, 5 to 300). Today's totals and
prices update every 60 seconds.

Which sensors exist depends on what your solar-dash has (`/api/capabilities`) and is
decided when the integration loads. Reload the integration after adding, for example,
Amber or a tariff to solar-dash.

## Entities

All entities belong to one **solar-dash** device. Names, units, classes and signs match
solar-dash's MQTT feed.

| Entity | Unit | Reads | Needs |
| --- | --- | --- | --- |
| Solar power | W | `/api/live` `sample.pv_w` | live |
| Home load | W | `sample.load_w` | live |
| Grid power (+import / -export) | W | `sample.grid_w` | live |
| Battery power (+charge / -discharge) | W | `sample.battery_w` | live |
| Battery state of charge | % | `sample.soc_pct` | live |
| Grid import | W | `max(sample.grid_w, 0)` | live |
| Grid export | W | `max(-sample.grid_w, 0)` | live |
| Grid import today | kWh | `/api/daily` `import_kwh` | live or history |
| Grid export today | kWh | `export_kwh` | live or history |
| Solar today | kWh | `pv_kwh` | live or history |
| Battery charge today | kWh | `battery_charge_kwh` | live or history |
| Battery discharge today | kWh | `battery_discharge_kwh` | live or history |
| Home use today | kWh | `load_kwh` | live or history |
| Power cost today | AUD | `/api/costs` day `import` minus `feed_in` | costs |
| Net cost today | AUD | `/api/costs` day `actual` | costs |
| Amber general price | c/kWh | `/api/prices` `now.general.cents` | prices |
| Amber feed-in price | c/kWh | `now.feed_in.cents`, sign flipped | prices |
| Amber price level | text | `now.general.descriptor` | prices |

- The "today" energy sensors use `total_increasing`, so they work in the Energy dashboard
  and reset at local midnight. "Today" is Home Assistant's local date, so solar-dash
  and Home Assistant should be in the same time zone.
- The feed-in price is shown as **earned**: Amber stores a negative number when you are
  paid, so it is flipped (a raw -8.3 shows as 8.3).
- When solar-dash has no fresh inverter sample, the live sensors show unknown.

## MQTT or this integration?

solar-dash can also publish the same sensors to Home Assistant over MQTT discovery.
Both give the same entities, so pick one and do not run both.

| | MQTT (built into solar-dash) | This integration |
| --- | --- | --- |
| Needs a broker | yes | no |
| Needs an API token | no | yes |
| Live updates | pushed | polled (15 s default) |
| Set up in | solar-dash `[home_assistant]` config | Home Assistant UI |

## Releasing

HACS installs from git tags and releases. To release, set `version` in
`custom_components/solar_dash/manifest.json`, then tag it: `git tag v0.1.0 && git push origin v0.1.0`.
The release workflow creates the GitHub release.

## Development

```sh
pip install -r requirements_test.txt
pytest
ruff check . && ruff format --check .
```
