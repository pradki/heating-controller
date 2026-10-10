# config.example.py - skopiuj do config.py i popraw adresy pod własną sieć.
import platform

# === MQTT ===
if platform.system() == "Linux":
    MQTT_BROKER_HOST = "localhost"
else:
    MQTT_BROKER_HOST = "192.168.1.10"

MQTT_BROKER_PORT = 1883
MQTT_CLIENT_ID = "heating_service"
MQTT_TOPIC_ROOT = "cave/heating"

MQTT_TOPICS = {
    "status": f"{MQTT_TOPIC_ROOT}/status",
    "control": f"{MQTT_TOPIC_ROOT}/control",
}

# === Wyjście: waveshare-mqtt-gateway ===
# Patrz github.com/pradki/waveshare-mqtt-gateway - ta usługa nie trzyma już
# własnego połączenia TCP do płytki przekaźników, tylko publikuje komendy.
RELAY_TOPIC_ROOT = "cave/relay"
RELAY_MODULE = "relay_heating"
SERVICE_NAME = "heating_service"
LEASE_PRIORITY = 10

# === Channels (Outputs) ===
# Numery kanałów na płytce Waveshare (te same, do których odwołuje się
# waveshare-mqtt-gateway/config.py pod aliasami co_fan, co_feeder, itd.)
# ignition: zdefiniowany, ale dziś nieużywany w heating.py - jeśli kiedyś
# zostanie podłączony, dobierz mu świadomie priority/ttl zamiast dziedziczyć
# wartości domyślne (to najbardziej bezpieczeństwo-krytyczny kanał na płytce).
# pump_boiler: używany przez Heating.pump_boiler_ctrl(), patrz niżej.
CHANNELS = {
    "fan": 26,
    "feeder": 25,
    "ignition": 10,
    "pump_boiler": 3,
    "pump_floor": 1,
    "valve_floor_close": 6,
    "valve_floor_open": [5, 6]
}

FEEDER_ON_TIME = 1.8
FEEDER_PAUSE = 20

# Sprzętowy impuls wentylatora odnawiany przez fan_keepalive() w heating.py
# (patrz tam komentarz) - niezależnie od tego, co akurat robi pętla decyzyjna.
FAN_FLASH_DURATION = 30
FAN_KEEPALIVE_MAX_AGE = 60

# Twardy, niezależny od furnace_temp_setpoint limit bezpieczeństwa - patrz
# Heating.is_overheated() w heating.py. furnace_temp_setpoint jest i tak
# zaciskany do 52-72°C przez shadow_vault, więc to dodatkowa warstwa na
# wypadek błędnej walidacji/configu, nie pierwsza linia obrony.
MAX_FURNACE_TEMP = 85

# Sterowanie podłogówką (zawór mieszający, pompa) świadomie wyłączone -
# niezadowalająca logika, w budowie osobny projekt. Kod zostaje w heating.py
# (inside_temp/mixing_valve_ctrl/check_overheated_floor), ale się nie uruchamia.
FLOOR_CONTROL_ENABLED = False

# Pompa podłogówki: jawny TTL i interwał odnawiania zamiast polegania na
# przypadkowej zbieżności z DEFAULT_LEASE_TTL gatewaya (patrz heating.py,
# mixing_valve_ctrl). Odnawiamy z dużym zapasem przed wygaśnięciem.
PUMP_LEASE_TTL = 1800
PUMP_RENEW_INTERVAL = 900

# === Pompa pieca (kanał "pump_boiler") ===
# Patrz Heating.pump_boiler_ctrl() - dwa niezależne powody uruchomienia:
# góra bufora przegrzana (bez pompy grzeje się tylko ona) albo piec przegrzany
# ponad zadaną o FURNACE_OVERHEAT_MARGIN (typowo zaraz po dorzuceniu drewna).
BUFF_TOP_PUMP_THRESHOLD = 65   # °C
FURNACE_OVERHEAT_MARGIN = 10   # °C ponad furnace_temp_setpoint
PUMP_BOILER_FLASH_DURATION = 180  # s, 3 min
PUMP_BOILER_CHECK_INTERVAL = 10   # s, jak często sprawdzamy oba warunki

# === Logging / History ===
LOG_DIRECTORY = "/home/sqna/heating/logs"
LOG_ROTATION_DAYS = 30
LOG_TEMPERATURE_AVG_INTERVAL = 3600  # 1h

# === Shadow Vault ===
SHADOW_FILE = "/home/sqna/heating/state.json"
