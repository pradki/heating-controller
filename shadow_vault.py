# cave/shadow_vault.py
# shadow - cień; pośrednik miedzy GUI a MQTT,
# Chroni przed zapętlaniem – bo wie, skąd przyszła zmiana i która jest nowsza.
# Chroni przed „pustym startem” – bo ma lokalny stan nawet bez brokera.
# Synchronizuje wiele widgetów – bo wszystkie widzą jeden wspólny bufor.
# Pozwala na rozłączanie MQTT bez utraty kontekstu.
# Ułatwia testy i debug – widać w JSON, co się dzieje.
# valut - skarbiec; wszystkie parametry w jednym miejscu


import time

DEFAULT = "default"
GUI = "gui"
BROKER = "broker"


# --- Definicja parametrów ---
PARAMS = {
    "outside_temp_sensor": {
        "name": "outside_temp_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 150.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura zewnętrzna",
        "topic": "cave/sensors/temperature/outside_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "general"
    },
    "inside_temp_sensor": {
        "name": "inside_temp_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 150.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura zewnętrzna",
        "topic": "cave/sensors/temperature/inside_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "general"
    },
    "floor_temp_sensor": {
        "name": "floor_temp_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 150.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura podłogówki",
        "topic": "cave/sensors/temperature/floor_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "general"
    },
    "buff_top_temp_sensor": {
        "name": "buff_top_temp_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 150.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura bufora górny czujnik",
        "topic": "cave/sensors/temperature/buff_top_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "general"
    },
    "buff_upmid_temp_sensor": {
        "name": "buff_upmid_temp_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 150.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura bufora środek górny czujnik",
        "topic": "cave/sensors/temperature/buff_upmid_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "general"
    },
    "buff_lowmid_temp_sensor": {
        "name": "buff_lowmid_temp_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 150.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura bufora środek dolny czujnik",
        "topic": "cave/sensors/temperature/buff_lowmid_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "general"
    },
    "buff_bot_temp_sensor": {
        "name": "buff_bot_temp_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 150.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura bufora dolny czujnik",
        "topic": "cave/sensors/temperature/buff_bot_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "general"
    },
    "mixing_valve_floor_position": {
        "name": "mixing_valve_floor_position",
        "value": None,
        "default": None,
        "min": 0,
        "max": 100,
        "data_type": "int",
        "unit": "s",
        "desc": "Pozycja otwarcia zaworu mieszającego",
        "topic": "cave/setvalue/mixing_valve_floor_position",
        "source": DEFAULT,
        "source_type": "setvalue",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "setvalue"
    },
    "scd30_main_temp_sensor": {
        "name": "scd30_main_temp_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 5000.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura czujnika CO2 main",
        "topic": "cave/sensors/temperature/scd30_main_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "general"
    },
    "scd30_main_airco2_sensor": {
        "name": "scd30_main_airco2_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 5000.0,
        "data_type": "float",
        "unit": "ppm",
        "desc": "Stężenie CO2",
        "topic": "cave/sensors/airco2/scd30_main_airco2",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "general"
    },
    "scd30_main_humidity_sensor": {
        "name": "scd30_main_humidity_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 5000.0,
        "data_type": "float",
        "unit": "%",
        "desc": "Wilgotność powierza",
        "topic": "cave/sensors/humidity/scd30_main_humidity",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "general"
    }
}

class Shadow:
    diff = False

    @classmethod
    def save_to_file(cls):
        pass


PARAMS_HEATING = {
    "furnace_enable_setpoint": {
        "name": "furnace_enable_setpoint",
        "value": True,
        "default": True,
        "min": False,
        "max": True,
        "data_type": "bool",
        "unit": "",
        "desc": "Włączenie/wyłączenie sterownika",
        "topic": "cave/heating/setpoints/furnace_enable",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,  # pending_pub i synced reprezentują ten sam stan w przeciwnej polaryzacji
        # # "synced": False,  # do usunięcia
        "category": "heating"
    },
    "furnace_temp_setpoint": {
        "name": "furnace_temp_setpoint",
        "value": 60,
        "default": 60,
        "min": 52,
        "max": 72,
        "data_type": "int",
        "unit": "°C",
        "desc": "Temperatura pieca (kotła CO)",
        "topic": "cave/heating/setpoints/furnace_temp",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "flue_gas_temp_setpoint": {
        "name": "flue_gas_temp_setpoint",
        "value": 55,
        "default": 55,
        "min": 20,
        "max": 200,
        "data_type": "int",
        "unit": "°C",
        "desc": "Temperatura spalin",
        "topic": "cave/heating/setpoints/flue_gas_temp",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "dhw_temp_setpoint": {
        "name": "dhw_temp_setpoint",
        "value": 55,
        "default": 55,
        "min": 30,
        "max": 75,
        "data_type": "int",
        "unit": "°C",
        "desc": "Domestic hot water (DHW) temperature, ogrzewania wody użytkowej (CWU)",
        "topic": "cave/heating/setpoints/dhw_temp",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "return_water_temp_setpoint": {
        "name": "return_water_temp_setpoint",
        "value": 45,
        "default": 45,
        "min": 30,
        "max": 75,
        "data_type": "int",
        "unit": "°C",
        "desc": "Temperatura powrotu, Zapobieganie kondensacji i korozji",
        "topic": "cave/heating/setpoints/return_water_temp",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "feeder_temp_setpoint": {
        "name": "feeder_temp_setpoint",
        "value": 85,
        "default": 85,
        "min": 15,
        "max": 120,
        "data_type": "int",
        "unit": "°C",
        "desc": "Temperatura podajnika, Ochrona przed zapłonem wstecznym w podajniku",
        "topic": "cave/heating/setpoints/feeder_temp",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "pause_time_setpoint": {
        "name": "pause_time_setpoint",
        "value": 120,
        "default": 120,
        "min": 30,
        "max": 300,
        "data_type": "int",
        "unit": "s",
        "desc": "Czas pauzy (między karmieniami)",
        "topic": "cave/heating/setpoints/pause_time",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "feeding_time_setpoint": {
        "name": "feeding_time_setpoint",
        "value": 9,
        "default": 9,
        "min": 3,
        "max": 30,
        "data_type": "int",
        "unit": "s",
        "desc": "Czas podawania (karmienia)",
        "topic": "cave/heating/setpoints/feeding_time",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "furnace_temp_sensor": {
        "name": "furnace_temp_sensor",
        "value": None,
        "default": None,
        "min": 0.0,
        "max": 120.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura pieca (kotła CO)",
        "topic": "cave/sensors/temperature/furnace_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "return_fireplace_temp_sensor": {
        "name": "return_fireplace_temp_sensor",
        "value": None,
        "default": None,
        "min": 0.0,
        "max": 120.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura na wejściu do kominka",
        "topic": "cave/sensors/temperature/return_fireplace_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "flue_gas_temp_sensor": {
        "name": "flue_gas_temp_sensor",
        "value": None,
        "default": None,
        "min": 20.0,
        "max": 200.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura spalin",
        "topic": "cave/sensors/temperature/flue_gas_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "dhw_temp_sensor": {
        "name": "dhw_temp_sensor",
        "value": None,
        "default": None,
        "min": -10.0,
        "max": 120.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Domestic hot water (DHW) temperature, ogrzewania wody użytkowej (CWU)",
        "topic": "cave/sensors/temperature/dhw_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "return_water_temp_sensor": {
        "name": "return_water_temp_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 150.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura powrotu, Zapobieganie kondensacji i korozji",
        "topic": "cave/sensors/temperature/return_water_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "feeder_temp_sensor": {
        "name": "feeder_temp_sensor",
        "value": None,
        "default": None,
        "min": -50.0,
        "max": 150.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura podajnika, Ochrona przed zapłonem wstecznym w podajniku",
        "topic": "cave/sensors/temperature/feeder_temp",
        "source": "sensor",
        "source_type": "sensor",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "keeping_fire_interval_setpoint": {
        "name": "keeping_fire_interval_setpoint",
        "value": 600,
        "default": 600,
        "min": 300,
        "max": 1800,
        "data_type": "int",
        "unit": "s",
        "desc": "Interwał między przedmuchami podtrzymującymi (co ile sekund włączyć dmuchawę)",
        "topic": "cave/heating/setpoints/keeping_fire_interval",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "keeping_fire_duration_setpoint": {
        "name": "keeping_fire_duration_setpoint",
        "value": 12,
        "default": 12,
        "min": 5,
        "max": 120,
        "data_type": "int",
        "unit": "s",
        "desc": "Czas trwania przedmuchu podtrzymującego (jak długo dmuchać)",
        "topic": "cave/heating/setpoints/keeping_fire_duration",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "multiplicity_setpoint": {
        "name": "multiplicity_setpoint",
        "value": 2,
        "default": 2,
        "min": 1,
        "max": 10,
        "data_type": "int",
        "unit": "",
        "desc": "co który cykl podawać",
        "topic": "cave/heating/setpoints/multiplicity",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "fan_speed_setpoint": {
        "name": "fan_speed_setpoint",
        "value": 50,
        "default": 50,
        "min": 0,
        "max": 100,
        "data_type": "int",
        "unit": "%",
        "desc": "Prędkość wentylatora (dmuchawy)",
        "topic": "cave/heating/setpoints/fan_speed",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "startup_temp_min_setpoint": {
        "name": "startup_temp_min_setpoint",
        "value": 40,
        "default": 40,
        "min": 20,
        "max": 60,
        "data_type": "int",
        "unit": "°C",
        "desc": "Minimalna temperatura startupu (limit rozgrzania)",
        "topic": "cave/heating/setpoints/startup_temp_min",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "startup_timeout_setpoint": {
        "name": "startup_timeout_setpoint",
        "value": 10,
        "default": 10,
        "min": 0,
        "max": 60,
        "data_type": "int",
        "unit": "s",
        "desc": "Maksymalny czas aby rozgrzać.",
        "topic": "cave/heating/setpoints/startup_timeout",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "mixing_valve_time_setpoint": {
        "name": "mixing_valve_time_setpoint",
        "value": 120,
        "default": 120,
        "min": 5,
        "max": 300,
        "data_type": "int",
        "unit": "s",
        "desc": "Czas otwierania zaworu mieszającego",
        "topic": "cave/heating/setpoints/mixing_valve_time",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    },
    "inside_temp_setpoint": {
        "name": "inside_temp_setpoint",
        "value": 21.2,
        "default": 21.3,
        "min": 15.0,
        "max": 28.0,
        "data_type": "float",
        "unit": "°C",
        "desc": "Temperatura wewnętrzna.",
        "topic": "cave/heating/setpoints/inside_temp",
        "source": DEFAULT,
        "source_type": "setpoint",
        "timestamp": 0,
        "pending_pub": False,
        # "synced": False,
        "category": "heating"
    }
}

params_heating = {}
for k, v in PARAMS_HEATING.items():
    if v["source_type"] == "sensor":
        k = k.replace('_sensor', "_1m")
        d = dict(v)
        d["name"] = k
        d["topic"] = f'{d["topic"].replace("sensors", "calculated")}_1m'
        d["source"] = "calculated"
        d["source_type"] = "calculated"
        params_heating[k] = d

PARAMS_HEATING.update(params_heating)

PARAMS.update(PARAMS_HEATING)

topic_param_map = {d["topic"]: param for param, d in PARAMS.items()}

# --- Funkcje API ---

def check_and_correct(param, value):
    p = PARAMS[param]
    try:
        if p["data_type"] == "bool":
            value = bool(value)
        elif (p["min"] is not None and value < p["min"]) or (p["max"] is not None and value > p["max"]):
            # raise ValueError(f"{name}: {value} out of range ({p['min']}–{p['max']})")
            value = p[DEFAULT]
    except:
        value = p[DEFAULT]
    return value

def update_from_gui(param, new_value):
    """Użytkownik zmienił wartość."""
    p = PARAMS[param]
    new_value = check_and_correct(param, new_value)
    if p["value"] != new_value:
        p["value"] = new_value
        p["source"] = GUI
        p["timestamp"] = time.time()  # time.monotonic()
        p["pending_pub"] = True
        # p["synced"] = False
        Shadow.diff = True
        print(f"[GUI] Zmieniono wartość na {new_value}, oczekuje publikacji")

def update_from_broker(param, new_value, timestamp=0):
    """Nowa wiadomość z brokera."""
    if param not in PARAMS:
        print(f'\x1b[31m#{__name__}:569# "{param}" not in PARAMS\x1b[0m')
        return
    p = PARAMS[param]
    new_value = check_and_correct(param, new_value)
    if p["value"] == new_value and p["timestamp"] == timestamp:
        # Echo lub potwierdzenie, nic nie rób
        print(f"[BROKER] Przyszło echo {new_value}, ignoruję")
        # p["synced"] = True  # synchronizowano
        p["pending_pub"] = False
        return

    # print(f'\t{p["timestamp"]=} {timestamp=}')
    if p["timestamp"] > timestamp:
        # GUI zmieniło niedawno, więc broker prawdopodobnie wysyła starą wartość
        print(f'[BROKER] Przyszło {new_value}, ale GUI było nowsze – ignoruję {p["timestamp"]=} {timestamp}')
        return

    # Akceptujemy zmianę z brokera
    p["value"] = new_value
    p["source"] = BROKER
    p["timestamp"] = timestamp  # time.monotonic()
    p["pending_pub"] = False
    Shadow.diff = True
    print(f"[BROKER:592] Nowa wartość z brokera: {new_value} [{param=}]")

def get(param, *args):
    """Return current value of a parameter."""
    if args:
        r = []
        item = PARAMS[param]
        r.append(item["value"])
        for key in args:
            r.append(item[key])
        return r

    return PARAMS[param]["value"]

def if_null_then_conditional_default(param, *args):
    """Return current value of a parameter."""
    value = PARAMS[param]["value"]
    if value is None:
        value = PARAMS[param]["default"]
    return value


def get_valid_sensor(param):
    timestamp = PARAMS[param]["timestamp"]
    if timestamp > time.monotonic() - 900:
        return PARAMS[param]["value"]


def get_topic(param):
    """Return topic of a parameter."""
    return PARAMS[param]["topic"]

def reset(param):
    """Reset parameter to its default value."""
    p = PARAMS[param]
    p["value"] = p[DEFAULT]
    p["source"] = DEFAULT
    p["timestamp"] = time.time()

def info(param):
    """Return full metadata for a given parameter."""
    return dict(PARAMS[param])  # copy to prevent external modification

def all_info():
    """Return dict with info about all parameters."""
    return {k: dict(v) for k, v in PARAMS.items()}

def describe(param):
    """Return human-readable description."""
    p = PARAMS[param]
    return (
        f"{p['name']}: {p['description']} "
        f"(default={p['default']}{p['unit']}, range={p['min']}–{p['max']})"
    )

def list_params():
    """Return list of all parameter names."""
    return list(PARAMS.keys())

def on_exit(self):
    if Shadow.diff:
        Shadow.save_to_file()
        Shadow.diff = False

async def autosave_loop(self):
    while True:
        await asyncio.sleep(60)
        if Shadow.diff:
            Shadow.save_to_file()
            Shadow.diff = False


def test():
    print(f'furnace_temp:{get("furnace_temp")} wartość domyślna:60')

    broker_timestamp = time.time()
    update_from_broker("furnace_temp", 63, timestamp=broker_timestamp)
    print(f'furnace_temp:{get("furnace_temp")} wartość:63')
    time.sleep(0.2)

    update_from_gui("furnace_temp", 62)
    gui_timestamp = PARAMS["furnace_temp"]["timestamp"]
    print(f'furnace_temp:{get("furnace_temp")} wartość:62')
    time.sleep(0.2)
    update_from_broker("furnace_temp", 62, timestamp=gui_timestamp)
    print(f'furnace_temp:{get("furnace_temp")} wartość:62')


if __name__ == "__main__":
    test()

# end.
