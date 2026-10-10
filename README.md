# heating-controller

Controls a wood/coal boiler (feeder auger, fan, ignition, pumps, floor mixing valve),
running as a standalone service on a Raspberry Pi. It reads sensors and setpoints over
MQTT and switches relays through
[waveshare-mqtt-gateway](https://github.com/pradki/waveshare-mqtt-gateway) - never
touching the relay board itself.

It is a rewrite of `heating_service` from [pradki/cave](https://github.com/pradki/cave),
kept behaviourally the same except for how relays are reached:

| | `heating_service` | this repo |
|---|---|---|
| Relay access | own Modbus-RTU-over-TCP connection to the board | MQTT commands to the gateway |
| Fan hardware pulse renewal | re-fired from inside the decision loop | a dedicated `fan_keepalive()` task, decoupled from the loop so a blocking retry in `feeder_temp()` can't lapse it (see below) |
| Floor pump lease | an hourly reset that happened to roughly match the gateway's default TTL | explicit `PUMP_LEASE_TTL` + `PUMP_RENEW_INTERVAL`, renewed well ahead of expiry |

## Install

```bash
cd /home/sqna/cave/raspberry
git clone git@github.com:pradki/heating-controller.git
cd heating-controller
/home/sqna/venv/cave/bin/pip install -r requirements.txt
cp config.example.py config.py   # then edit config.py - see Configuration below
sudo cp heating-controller.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now heating-controller
```

Don't run this alongside the old `heating.service` (`heating_service/heating.py`) at the
same time - both would fight over the same relay channels.

## Configuration

`config.py` (gitignored - `config.example.py` is the tracked template) holds the MQTT
broker address, the gateway's module name (`RELAY_MODULE`, must match a module already
configured in `waveshare-mqtt-gateway/config.py`), the physical channel numbers
(`CHANNELS`), and the relay-lease tuning described below.

`ignition` and `pump_boiler` are defined in `CHANNELS` but not wired into any control
logic today (a gap that predates this migration, carried over as-is). If they get wired
up later, give them a deliberately-chosen `priority`/`ttl` rather than inheriting
defaults - `ignition` in particular is the most safety-sensitive channel on the board.

## Why a separate fan keep-alive task

`heating()`'s decision loop wants the fan on continuously while the furnace is below
setpoint, re-asserting that need roughly every 6 seconds. But `feeder_temp()` - called
every iteration, to catch live fire sitting in the feeder auger - can block for up to
~24 minutes in its worst-case retry path. If the fan's hardware pulse were only renewed
from inside that same loop, a long `feeder_temp()` retry could let the pulse lapse and
the fan drop out mid-heating. `fan_keepalive()` runs as its own ~10s loop, re-firing the
pulse as long as the decision ("I still want the fan") is fresher than
`FAN_KEEPALIVE_MAX_AGE` - independent of whatever `heating()` happens to be blocked on,
but still fail-safe if the decision loop itself hangs.

`keeping_fire()`'s fan blow is different in kind - a single, deliberately-timed pulse
(`keeping_fire_duration_setpoint`, typically ~12s), not a continuous need - so it's left
as a direct one-shot call, unaffected by `fan_keepalive()`.

## Known accepted risk: floor valve two-pulse timing

`set_mixing_valve()` drives the floor mixing valve's `valve_floor_open` position with two
sequential channel pulses (slightly different durations, by design - see the code
comment). Under direct Modbus this was two back-to-back synchronous calls; over MQTT,
gateway delivery can add up to ~1s of jitter between them if they straddle the gateway's
1Hz reconcile tick. Assumed to be absorbed by the mechanical actuator's own response time;
revisit only if floor valve position drift is ever observed.

## Files

| File | Role |
|---|---|
| `main.py` | Entry point - wires up MQTT, the gateway relay client, and `Heating` |
| `heating.py` | Control logic: feeder/fan/keeping-fire state machine, floor mixing valve, inside-temperature averaging |
| `relay_client.py` | `GatewayRelay` - thin MQTT command publisher to waveshare-mqtt-gateway, channel-number addressed |
| `manager.py` / `shadow_vault.py` | Sensor/setpoint shadow store (MQTT-backed, survives disconnects) |
| `mqtt_controller.py` | MQTT client thread (paho-mqtt) |
| `feeder_logger.py` | CSV on-time logging for the feeder and temperature averages |
| `heating-controller.service` | systemd unit |
| `tests/` | Fake-broker tests for `GatewayRelay` (no MQTT broker or hardware required) |

---

Part of [pradki/cave](https://github.com/pradki/cave). Code comments are in Polish.
