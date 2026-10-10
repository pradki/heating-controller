# heating-controller

Controls a wood/coal boiler (feeder auger, fan, keeping-fire/overheat logic), running as
a standalone service on a Raspberry Pi. It reads sensors and setpoints over MQTT and
switches relays through
[waveshare-mqtt-gateway](https://github.com/pradki/waveshare-mqtt-gateway) - never
touching the relay board itself. Floor-circuit control is present in the code but
disabled - see "Scope" below.

It is a rewrite of `heating_service` from [pradki/cave](https://github.com/pradki/cave),
kept behaviourally the same except for how relays are reached:

| | `heating_service` | this repo |
|---|---|---|
| Relay access | own Modbus-RTU-over-TCP connection to the board | MQTT commands to the gateway |
| Fan hardware pulse renewal | re-fired from inside the decision loop | a dedicated `fan_keepalive()` task, decoupled from the loop so a blocking retry in `feeder_temp()` can't lapse it (see below) |
| Floor pump lease | an hourly reset that happened to roughly match the gateway's default TTL | explicit `PUMP_LEASE_TTL` + `PUMP_RENEW_INTERVAL`, renewed well ahead of expiry |
| Furnace overheat protection | only the user-settable setpoint comparison | same, plus an independent hard ceiling (`MAX_FURNACE_TEMP`, see below) |
| Floor mixing valve / floor pump | active (`mixing_valve_ctrl`, `inside_temp`) | disabled (`config.FLOOR_CONTROL_ENABLED = False`) - unsatisfactory control logic, being redesigned separately; code kept in place, not deleted, so it's easy to pick back up |

## Scope: furnace only, floor heating control disabled

This controller now drives only the furnace itself - feeder, fan, and the
temperature/keeping-fire state machine. Floor-circuit control (the mixing valve and
floor pump, `mixing_valve_ctrl()`/`inside_temp()`/`check_overheated_floor()` in
`heating.py`) is **disabled**, not deleted: `config.FLOOR_CONTROL_ENABLED = False` simply
skips starting that task chain in `Heating.main()`. A separate, from-scratch floor
heating controller is planned; until then this code sits dormant as reference. The
`pump_floor`/`valve_floor_open`/`valve_floor_close` channels stay defined in
`config.CHANNELS` (and the `"pump_floor"` key stays in the published status JSON,
always `None`) for compatibility with anything still reading that shape.

## Furnace overheat safety: two independent layers

1. **Setpoint bound**: `furnace_temp_setpoint` is clamped to 52-72°C by
   `shadow_vault.check_and_correct` regardless of what's requested over MQTT/GUI, and a
   stale `furnace_temp_sensor` reading (no update in 15 minutes) is treated as "no data"
   and stops heating (fail-safe direction).
2. **Hard ceiling, independent of the setpoint**: `Heating.is_overheated()` checks
   `furnace_temp_sensor` against `config.MAX_FURNACE_TEMP` (85°C) directly - not through
   the setpoint at all. If it trips, `feed_now()` refuses to fire the feeder (checked
   once, so every call site is covered), `fan_keepalive()` stops renewing the fan's
   pulse, and both `heating()`/`keeping_fire()` skip their feed/blow cycles and publish
   an `"overheat"` state. This is a second, independent net for the case where the first
   layer's validation is ever bypassed or misconfigured - under normal operation the
   setpoint bound trips first, since 85°C is above any value the setpoint can hold.

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

`ignition` is defined in `CHANNELS` but not wired into any control logic today (a gap
that predates this migration, carried over as-is). If it gets wired up later, give it a
deliberately-chosen `priority`/`ttl` rather than inheriting defaults - it's the most
safety-sensitive channel on the board. `pump_boiler` *is* wired up - see below.

## Boiler pump (`pump_boiler`)

`Heating.pump_boiler_ctrl()` checks two independent conditions every
`PUMP_BOILER_CHECK_INTERVAL` (10s) and fires a `PUMP_BOILER_FLASH_DURATION` (3 min) pulse
whenever either holds:

1. **Buffer top above `BUFF_TOP_PUMP_THRESHOLD`** (65°C) - without circulation, only the
   top layer of the buffer tank heats up; the pump moves that heat down into the lower
   layers so the whole tank's capacity gets used.
2. **Furnace above `furnace_temp_setpoint + FURNACE_OVERHEAT_MARGIN`** (10°C) - typically
   right after adding wood/coal and the furnace temperature spikes; the pump bleeds the
   excess into the buffer before the harder `MAX_FURNACE_TEMP` cutoff (`is_overheated()`)
   would have to step in.

Like `fan_keepalive()`, this is only a *renewer* of a hardware-timed pulse: if the task
hangs or the service crashes, the pump still turns itself off after
`PUMP_BOILER_FLASH_DURATION` instead of being stuck on. Both conditions are evaluated
independently of `is_overheated()` and keep running even while it has tripped - pulling
heat out of the furnace into the buffer is the right thing to do precisely when the
furnace is overheating, not something to suppress. The active reason (or `None`) is
visible in the status payload as `pump_boiler`.

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

## Known accepted risk: floor valve two-pulse timing (dormant code, for whenever this is revisited)

`set_mixing_valve()` (currently unreachable - see "Scope" above) drives the floor mixing
valve's `valve_floor_open` position with two sequential channel pulses (slightly
different durations, by design - see the code comment). Under direct Modbus this was two
back-to-back synchronous calls; over MQTT, gateway delivery can add up to ~1s of jitter
between them if they straddle the gateway's 1Hz reconcile tick. Worth re-checking before
this code is ever re-enabled or rebuilt.

## Files

| File | Role |
|---|---|
| `main.py` | Entry point - wires up MQTT, the gateway relay client, and `Heating` |
| `heating.py` | Control logic: feeder/fan/keeping-fire state machine, overheat safety; floor mixing valve + inside-temperature averaging present but disabled (`config.FLOOR_CONTROL_ENABLED`) |
| `relay_client.py` | `GatewayRelay` - thin MQTT command publisher to waveshare-mqtt-gateway, channel-number addressed |
| `manager.py` / `shadow_vault.py` | Sensor/setpoint shadow store (MQTT-backed, survives disconnects) |
| `mqtt_controller.py` | MQTT client thread (paho-mqtt) |
| `feeder_logger.py` | CSV on-time logging for the feeder and temperature averages |
| `heating-controller.service` | systemd unit |
| `tests/` | Fake-broker tests for `GatewayRelay` (no MQTT broker or hardware required) |

---

Part of [pradki/cave](https://github.com/pradki/cave). Code comments are in Polish.
