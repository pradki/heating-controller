
import asyncio
import time
import json
import datetime
from collections import deque

from feeder_logger import FeederLogger, CsvLogger
import config

feeder_log = FeederLogger(filename="feeder_log.csv")

CSV_SENSOR = [
    "outside_temp_sensor",
    "inside_temp_sensor",
    "floor_temp_sensor",
    "buff_top_temp_sensor",
    "buff_upmid_temp_sensor",
    "buff_lowmid_temp_sensor",
    "buff_bot_temp_sensor",
    "furnace_temp_sensor",
    "return_fireplace_temp_sensor",
    "flue_gas_temp_sensor",
    "dhw_temp_sensor",
    "return_water_temp_sensor",
    "feeder_temp_sensor",
    "scd30_main_temp_sensor",
    "scd30_main_airco2_sensor",
    "scd30_main_humidity_sensor"
]
temp_log = CsvLogger("temp_ave.csv", CSV_SENSOR)
_monotonic_begin = time.monotonic()

class Aves:

    def __init__(self, sensors):
        self.sensors = {}

        for sensor in sensors:
            self.sensors[sensor] = Ave()

class Ave:
    # minute, quarter of an hour, hour, day.

    def __init__(self):
        ts = int(time.time())
        self.ts_min = ts // 60              # minute
        self.ts_qtr = self.ts_min // 15     # quarter of an hour
        self.ts_hour = self.ts_qtr // 4     # hour
        self.ts_day = self.ts_hour // 24    # day

        self.de_min = deque(maxlen=5)       #  5 sample 12s
        self.de_qtr = deque(maxlen=15)      # 15 sample minute
        self.de_hour = deque(maxlen=4)      #  4 sample quarter
        self.de_day = deque(maxlen=24)      # 24 sample hour

    def ave(self, de):
        l = [d for d in de if d is not None]
        if l:
            r = sum(l) / len(l)
        else:
            r = None
        return r

    def add(self, ts_min, value):
        if self.ts_min != ts_min:
            self.de_qtr.append(self.ave(self.de_min))
            self.ts_min = ts_min
            ts_qtr = ts_min // 15
            if self.ts_qtr != ts_qtr:
                self.de_hour.append(self.ave(self.de_qtr))
                self.ts_qtr = ts_qtr
                ts_hour = ts_qtr // 4
                if self.ts_hour != ts_hour:
                    self.de_day.append(self.ave(self.de_hour))
                    self.ts_hour = ts_hour
        self.de_min.append(value)

    def get_day(self):
        if len(self.de_day) > 7:
            return self.ave(self.de_day)

    def get_hour(self, idx):
        if idx < 0:
            if abs(idx) > len(self.de_day):
                idx = -1 * len(self.de_day)
        else:
            if idx >= len(self.de_day):
                idx = len(self.de_day) - 1
        if len(self.de_day):
            return self.de_day[idx]
        if len(self.de_hour):
            return self.de_hour[-1]
        if len(self.de_qtr):
            return self.de_qtr[-1]
        if len(self.de_min):
            return self.de_min[-1]

    def get_qtr(self, idx):
        if idx < 0:
            if abs(idx) > len(self.de_hour):
                idx = -1 * len(self.de_hour)
        else:
            if idx >= len(self.de_hour):
                idx = len(self.de_hour) - 1
        if len(self.de_hour):
            return self.de_hour[idx]
        if len(self.de_qtr):
            return self.de_qtr[-1]
        if len(self.de_min):
            return self.de_min[-1]

    def get_min(self, idx):
        if idx < 0:
            if abs(idx) > len(self.de_qtr):
                idx = -1 * len(self.de_qtr)
        else:
            if idx >= len(self.de_qtr):
                idx = len(self.de_qtr) - 1

        if len(self.de_qtr):
            return self.de_qtr[idx]
        if len(self.de_min):
            return self.de_min[-1]


ave_temps = Aves(CSV_SENSOR)


class Heating:
    mqtt_pub_callback = None
    relays = None
    is_connected_callback = None
    _state = "pending"
    _state_desc = "pending"
    _enable = False
    # initing - czekamy na furnace_temp_sensor różną od None
    # heating - gdy temperatura furnace_temp_sensor mniejsza o zadanej furnace_temp_setpoint
    # keeping_fire - podtrzymanie / przedmuch

    ds = None
    callback_feeding = None

    feeding_timestamp = 0  # time.monotonic()
    pump_floor = None
    mixing_valve_floor_position = 0  # 0-close; 100%-open
    mixing_valve_status = {
        "overheated_floor": None,
        "temperature_is_stable": None,
        "delta_inside": None
    }

    # Wentylator w heating() ma być włączony cały czas, dopóki furnace_temp <
    # setpoint - ale feeder_temp() potrafi zablokować tę pętlę na 30-90s na
    # próbę (do ~24 min w najgorszym razie), więc odnawianie sprzętowego
    # impulsu jest wydzielone do fan_keepalive(), niezależnej pętli. Patrz
    # fan_keepalive().
    fan_wanted = False
    fan_last_decision_ts = 0  # time.monotonic()

    # Pompa pieca (kanał "pump_boiler") - patrz pump_boiler_ctrl(). None, dopóki
    # żaden z dwóch powodów nie trwa; w przeciwnym razie krótki opis, dlaczego
    # pompa jest akurat żądana (do statusu/diagnostyki).
    pump_boiler_reason = None

    @classmethod
    def is_overheated(cls):
        """Twardy, niezależny od furnace_temp_setpoint limit bezpieczeństwa -
        setpoint sam jest już zaciskany do 52-72°C przez shadow_vault
        (check_and_correct) i nieaktualny czujnik już dziś wyłącza grzanie
        (fail-safe w pętlach heating()/keeping_fire()), ale to dodatkowa
        warstwa niezależna od poprawności configu/walidacji nastaw: jeśli
        furnace_temp_sensor i tak przekroczy MAX_FURNACE_TEMP, przestajemy
        karmić i dmuchać bez względu na to, co mówi reszta logiki."""
        furnace_temp_sensor = cls.ds.get_valid_sensor('furnace_temp_sensor')
        return furnace_temp_sensor is not None and furnace_temp_sensor >= config.MAX_FURNACE_TEMP

    @classmethod
    def state(cls, state=None, desc=""):
        if state is None:
            return cls._state

        cls._state = state
        cls._state_desc = desc
        if cls.mqtt_pub_callback:
            topic = 'cave/heating/status/'
            msg = json.dumps({
                "enable": cls._enable,
                "state": cls._state,
                "desc": cls._state_desc,
                "monotonic": time.monotonic(),
                "uptime": time.monotonic() - _monotonic_begin,
                "feeding_timestamp": cls.feeding_timestamp,
                "feeding_delta": time.monotonic() - cls.feeding_timestamp,
                "pump_floor": cls.pump_floor,
                "pump_boiler": cls.pump_boiler_reason,
                "mqtt_connected": cls.is_connected_callback() if cls.is_connected_callback else None,
            })
            cls.mqtt_pub_callback(topic, msg)

    @classmethod
    async def valve_state(cls):
        while True:
            await asyncio.sleep(20)

            try:
                if cls.mqtt_pub_callback:
                    topic = 'cave/heating/valve_status/'
                    mixing_valve_status = {
                        "mixing_valve_floor_position": cls.mixing_valve_floor_position,
                        "pump_floor": cls.pump_floor
                    }
                    mixing_valve_status.update(cls.mixing_valve_status)
                    msg = json.dumps(mixing_valve_status)
                    cls.mqtt_pub_callback(topic, msg)

                    topic = 'cave/setvalue/mixing_valve_floor_position'
                    mixing_valve_status = {
                        "value": cls.mixing_valve_floor_position,
                        "timestamp": time.time()
                    }
                    msg = json.dumps(mixing_valve_status)
                    cls.mqtt_pub_callback(topic, msg)

            except Exception as e:
                print(f'\x1b[31m#{__name__}:198# {type(e).__name__} "{e}"\x1b[0m')


    @classmethod
    def init(cls, ds, mqtt_pub_callback, relays, is_connected=None):
        cls.ds = ds
        cls.mqtt_pub_callback = mqtt_pub_callback
        cls.relays = relays
        cls.is_connected_callback = is_connected
        cls.feeding_timestamp = 0  # karmienie (podawanie) time.monotonic()

    @classmethod
    async def feed_now(cls):
        if cls.is_overheated():
            print(f'\x1b[31m#{__name__}:feed_now# pominięto - piec przegrzany (>={config.MAX_FURNACE_TEMP}°C)\x1b[0m')
            return
        feeding_time_setpoint = cls.ds.get_value_setpoint('feeding_time_setpoint')
        await cls.relays.relay_flash_on(config.CHANNELS["feeder"], timeout=feeding_time_setpoint)
        await feeder_log.add_seconds(feeding_time_setpoint)
        cls.feeding_timestamp = time.monotonic()

    @classmethod
    async def fan_keepalive(cls):
        """Odnawia sprzętowy impuls wentylatora z własnej, krótkiej pętli -
        niezależnie od heating()'s loop, która potrafi utknąć w feeder_temp()
        na długo. Ping tylko dopóki decyzja "chcę wentylator" jest świeża
        (FAN_KEEPALIVE_MAX_AGE), żeby zawieszona pętla decyzyjna nie trzymała
        wentylatora w nieskończoność - to jest watchdog, nie tylko odnawiacz."""
        while True:
            await asyncio.sleep(10)
            if cls.is_overheated():
                continue
            if cls.fan_wanted and (time.monotonic() - cls.fan_last_decision_ts) < config.FAN_KEEPALIVE_MAX_AGE:
                try:
                    await cls.relays.relay_flash_on(config.CHANNELS["fan"], timeout=config.FAN_FLASH_DURATION)
                except Exception as e:
                    print(f'\x1b[31m#{__name__}:fan_keepalive# {type(e).__name__} "{e}"\x1b[0m')

    @classmethod
    async def pump_boiler_ctrl(cls):
        """Pompa pieca (kanał "pump_boiler") - przenosi ciepło z dwóch
        niezależnych powodów, sprawdzanych co PUMP_BOILER_CHECK_INTERVAL:

        1) góra bufora > BUFF_TOP_PUMP_THRESHOLD - bez pompy grzeje się tylko
           górna partia bufora; pompa rozprowadza ciepło na niższe warstwy.
        2) piec > zadana + FURNACE_OVERHEAT_MARGIN - typowo zaraz po
           dorzuceniu drewna; pompa odprowadza nadmiar do bufora, zanim
           zadziała twardy limit is_overheated() (MAX_FURNACE_TEMP).

        Jak fan_keepalive(): to tylko odnawiacz sprzętowego impulsu
        (PUMP_BOILER_FLASH_DURATION) - jeśli ten task się zawiesi albo usługa
        padnie, pompa i tak zgaśnie sama po czasie impulsu, nie zostaje
        włączona na stałe."""
        while True:
            await asyncio.sleep(config.PUMP_BOILER_CHECK_INTERVAL)

            buff_top = cls.ds.get_valid_sensor('buff_top_temp_sensor')
            furnace_temp = cls.ds.get_valid_sensor('furnace_temp_sensor')
            furnace_setpoint = cls.ds.get_value_setpoint('furnace_temp_setpoint')

            reason = None
            if buff_top is not None and buff_top > config.BUFF_TOP_PUMP_THRESHOLD:
                reason = f"bufor góra {buff_top:.1f}>{config.BUFF_TOP_PUMP_THRESHOLD}C"
            elif (furnace_temp is not None and furnace_setpoint is not None
                  and furnace_temp > furnace_setpoint + config.FURNACE_OVERHEAT_MARGIN):
                reason = (f"piec {furnace_temp:.1f}>zadana {furnace_setpoint:.1f}"
                          f"+{config.FURNACE_OVERHEAT_MARGIN}C")

            cls.pump_boiler_reason = reason
            if reason:
                try:
                    await cls.relays.relay_flash_on(config.CHANNELS["pump_boiler"],
                                                    timeout=config.PUMP_BOILER_FLASH_DURATION)
                except Exception as e:
                    print(f'\x1b[31m#{__name__}:pump_boiler_ctrl# {type(e).__name__} "{e}"\x1b[0m')

    @classmethod
    async def heating(cls):  # dogrzewanie zbyt niska temperatura
        cls.state("heating")  # dogrzewanie

        # feeding_time_setpoint czas karmienia
        # pause_time_setpoint czas przerwy między karmieniem

        while True:
            furnace_temp_sensor = cls.ds.get_valid_sensor('furnace_temp_sensor')
            furnace_temp_setpoint = cls.ds.get_value_setpoint('furnace_temp_setpoint')
            print(f'#{__name__}:54# {furnace_temp_sensor=} {furnace_temp_setpoint=}')
            if not furnace_temp_sensor or furnace_temp_sensor > furnace_temp_setpoint:
                print(f'#{__name__}:79# break')
                cls.state("end of heating", desc=f"{furnace_temp_sensor=} {furnace_temp_setpoint=}")  # dogrzewanie
                break

            if cls.is_overheated():
                cls.fan_wanted = False
                cls.state("overheat", desc=f"{furnace_temp_sensor=} >= MAX_FURNACE_TEMP={config.MAX_FURNACE_TEMP}")
                await asyncio.sleep(6)
                continue

            # włączyć wentylator - odnawiane niezależnie przez fan_keepalive()
            cls.fan_wanted = True
            cls.fan_last_decision_ts = time.monotonic()

            monotonic = time.monotonic()
            pause_time_setpoint = cls.ds.get_value_setpoint('pause_time_setpoint')
            if pause_time_setpoint is None:
                pause_time_setpoint = 121

            if cls.feeding_timestamp < monotonic - pause_time_setpoint:
                print('\x1b[33mfeed_now():277\x1b[0m')
                print(f'\x1b[33m{cls.feeding_timestamp=} < {monotonic=} - {pause_time_setpoint=}\x1b[0m')
                await cls.feed_now()
                cls.state("heating (feeding)", desc=f"{furnace_temp_sensor=} < {furnace_temp_setpoint=}")  # dogrzewanie
            else:
                cls.state("heating (pause)", desc=f"{furnace_temp_sensor=} < {furnace_temp_setpoint=} pause:{cls.feeding_timestamp - (monotonic - pause_time_setpoint)}")  # dogrzewanie

            await cls.feeder_temp()
            await asyncio.sleep(6)
        # wyłączyć wentylator - fan_wanted zostaje True do FAN_KEEPALIVE_MAX_AGE,
        # potem gaśnie samo (tak jak dziś gasł sprzętowy impuls bez odnowienia)

    @classmethod
    async def keeping_fire(cls):  # temperatura jest ok, tylko podtrzymanie ognia
        cls.state("keeping_fire")  # dogrzewanie
        # krotność
        multiplicity = 0
        while True:
            multiplicity_setpoint = cls.ds.get_value_setpoint('multiplicity_setpoint')
            if multiplicity_setpoint is None:
                multiplicity_setpoint = 2

            furnace_temp_sensor = cls.ds.get_valid_sensor('furnace_temp_sensor')
            furnace_temp_setpoint = cls.ds.get_value_setpoint('furnace_temp_setpoint')
            print(f'#{__name__}:54# {furnace_temp_sensor=} {furnace_temp_setpoint=}')
            if not furnace_temp_sensor or furnace_temp_sensor < furnace_temp_setpoint:
                print(f'#{__name__}:113# break')
                break

            if cls.is_overheated():
                cls.state("overheat", desc=f"{furnace_temp_sensor=} >= MAX_FURNACE_TEMP={config.MAX_FURNACE_TEMP}")
                await asyncio.sleep(6)
                continue

            monotonic = time.monotonic()
            keeping_fire_interval_setpoint = cls.ds.get_value_setpoint('keeping_fire_interval_setpoint')
            if keeping_fire_interval_setpoint is None:
                keeping_fire_interval_setpoint = 601

            keeping_fire_duration_setpoint = cls.ds.get_value_setpoint('keeping_fire_duration_setpoint')

            if cls.feeding_timestamp < monotonic - keeping_fire_interval_setpoint:
                # przedmuch keeping_fire_duration_setpoint - jednorazowy impuls o
                # kontrolowanym czasie trwania, celowo NIE przez fan_keepalive()
                # (to nie jest "trzymaj wentylator", tylko krótki, odmierzony przedmuch)
                multiplicity += 1

                await cls.relays.relay_flash_on(config.CHANNELS["fan"], timeout=keeping_fire_duration_setpoint)
                await asyncio.sleep(6)
                if not multiplicity % multiplicity_setpoint:
                    print('\x1b[33mfeed_now():326\x1b[0m')
                    print(f'\x1b[33m{multiplicity=} % {multiplicity_setpoint=}\x1b[0m')
                    await cls.feed_now()
                cls.feeding_timestamp = monotonic
                cls.state("keeping_fire (keeping)", desc=f"{furnace_temp_sensor=} < {furnace_temp_setpoint=}")  # dogrzewanie
            else:
                cls.state("keeping_fire (pause)", desc=f"{furnace_temp_sensor=} < {furnace_temp_setpoint=} pause:{cls.feeding_timestamp - (monotonic - keeping_fire_duration_setpoint)}")  # dogrzewanie
            await cls.feeder_temp()
            await asyncio.sleep(6)

    @classmethod
    async def feeder_temp(cls):  # żar w podajniku
        state = cls.state()
        feeder_temp_last = cls.ds.get_valid_sensor('feeder_temp_sensor')
        for x in range(12):
            feeder_temp_sensor = cls.ds.get_valid_sensor('feeder_temp_sensor')
            feeder_temp_setpoint = cls.ds.get_value_setpoint('feeder_temp_setpoint')
            if feeder_temp_sensor > feeder_temp_setpoint:
                # podaj węgiel
                cls.state("fire_in_feeder")
                print('\x1b[33mfeed_now():351\x1b[0m')
                print(f'\x1b[33m{feeder_temp_sensor=} > {feeder_temp_setpoint=}\x1b[0m')
                await cls.feed_now()
                await asyncio.sleep(30)
            else:
                break
        if feeder_temp_last > cls.ds.get_valid_sensor('feeder_temp_sensor'):
            for x in range(12):
                feeder_temp_sensor = cls.ds.get_valid_sensor('feeder_temp_sensor')
                feeder_temp_setpoint = cls.ds.get_value_setpoint('feeder_temp_setpoint')
                if feeder_temp_last < cls.ds.get_valid_sensor('feeder_temp_sensor'):
                    break
                elif feeder_temp_sensor > feeder_temp_setpoint:
                    # podaj węgiel
                    cls.state("fire_in_feeder")
                    print('\x1b[33mfeed_now():365\x1b[0m')
                    print(f'\x1b[33m{feeder_temp_sensor=} > {feeder_temp_setpoint=}\x1b[0m')
                    await cls.feed_now()
                    await asyncio.sleep(90)
                else:
                    break

        if cls.state() != state:
            cls.state(state)

    @classmethod
    async def main(cls):
        # czekam aż będą dane z sensorów, nie dłużej niż 2 minuty
        for _ in range(20):
            cls.state("initing")
            furnace_temp_sensor = cls.ds.get_valid_sensor('furnace_temp_sensor')
            print(f'#{__name__}:74# {furnace_temp_sensor=} {cls.state()}.. ({_})')
            if furnace_temp_sensor is not None:
                break
            await asyncio.sleep(6)

        await asyncio.sleep(10)
        if config.FLOOR_CONTROL_ENABLED:
            # Sterowanie podłogówką (zawór mieszający, pompa, uśrednianie
            # inside_temp) wyłączone świadomie - w budowie osobna logika,
            # patrz config.FLOOR_CONTROL_ENABLED i README.
            print('czekam:215..')
            task_inside_temp = asyncio.create_task(cls.inside_temp())
            print('czekam:217..')
        await asyncio.sleep(10)

        while True:
            cls._enable = cls.ds.get_value_setpoint('furnace_enable')
            print(f'#{__name__}:110# {cls.state()}')
            if not cls._enable:

                await asyncio.sleep(6)
                continue
            await cls.heating()
            print(f'#{__name__}:114# {cls.state()}')
            await cls.keeping_fire()
            cls.state("next")  # podtrzymanie
            print(f'#{__name__}:116# {cls.state()}')
            await asyncio.sleep(6)

    @classmethod
    async def ave(cls):
        while True:
            for key, sensor in ave_temps.sensors.items():
                try:
                    if cls.mqtt_pub_callback:
                        topic = f'cave/sensors/ave/{key}'
                        msg = json.dumps({
                            "min": list(sensor.de_min),
                            "qtr": list(sensor.de_qtr),
                            "hour": list(sensor.de_hour),
                            "day": list(sensor.de_day),
                            "monotonic": time.monotonic()
                        })
                        cls.mqtt_pub_callback(topic, msg)
                except Exception as e:
                    print(f'\x1b[31m#{__name__}:428# {type(e).__name__} "{e}"\x1b[0m')
            await asyncio.sleep(12)

    @classmethod
    async def mixing_valve_ctrl(cls):
        print(f'\x1b[36m#{__name__}:373# mixing_valve_ctrl\x1b[0m')
        pump_floor = None
        mixing_valve_floor_position = 0
        mixing_valve_floor_ts = time.monotonic()
        # Czas ostatniego faktycznie wysłanego relay_on/relay_off dla pump_floor -
        # renewal dzieje się z wyprzedzeniem przed PUMP_LEASE_TTL, nie na
        # przypadkowej zbieżności z jakimś innym interwałem w tej pętli.
        last_pump_renew = 0.0

        async def punp_on():
            nonlocal last_pump_renew
            print(f'\x1b[36m#{__name__}:381# mixing_valve_ctrl\x1b[0m')

            for x in range(3):
                try:
                    await cls.relays.relay_on(config.CHANNELS["pump_floor"], ttl=config.PUMP_LEASE_TTL)
                    last_pump_renew = time.monotonic()
                    break
                except:
                    continue

        async def punp_off():
            nonlocal last_pump_renew
            print(f'\x1b[36m#{__name__}:391# mixing_valve_ctrl\x1b[0m')

            for x in range(3):
                try:
                    await cls.relays.relay_off(config.CHANNELS["pump_floor"], ttl=config.PUMP_LEASE_TTL)
                    last_pump_renew = time.monotonic()
                    break
                except:
                    continue

        async def set_mixing_valve(value):
            print(f'\x1b[36m#{__name__}:410# set_mixing_valve\x1b[0m')
            tb = time.monotonic()
            try:
                if value < 0:
                    chnl = config.CHANNELS["valve_floor_close"]
                    if isinstance(chnl, list):
                        await cls.relays.relay_flash_on(chnl[0], timeout=abs(value)+3)
                        await cls.relays.relay_flash_on(chnl[1], timeout=abs(value))
                    else:
                        await cls.relays.relay_flash_on(chnl, timeout=abs(value))
                else:
                    chnl = config.CHANNELS["valve_floor_open"]
                    if isinstance(chnl, list):
                        await cls.relays.relay_flash_on(chnl[0], timeout=abs(value)+1)
                        await cls.relays.relay_flash_on(chnl[1], timeout=abs(value))
                    else:
                        await cls.relays.relay_flash_on(chnl, timeout=abs(value))
            except Exception as e:
                print(f'\x1b[31m#{__name__}:428# {type(e).__name__} "{e}"\x1b[0m')
                pass
            te = time.monotonic()
            await asyncio.sleep(value - (te-tb))

        await set_mixing_valve(-150)
        mixing_valve_floor_position = 0

        while True:
            print(f'\x1b[36m#{__name__}:455# task mixing_valve {cls.mixing_valve_floor_position=}\x1b[0m')
            await asyncio.sleep(10)
            try:
                if pump_floor != cls.pump_floor:
                    if cls.pump_floor:
                        await punp_on()
                    else:
                        await punp_off()
                    pump_floor = cls.pump_floor
                elif cls.pump_floor and (time.monotonic() - last_pump_renew) > config.PUMP_RENEW_INTERVAL:
                    # odnawiamy lease na "on" z wyprzedzeniem - "off" nie trzeba:
                    # brak lease'u i tak domyślnie znaczy "off" na gatewayu
                    await punp_on()

                if mixing_valve_floor_position != cls.mixing_valve_floor_position:
                    await set_mixing_valve(cls.mixing_valve_floor_position - mixing_valve_floor_position)
                    mixing_valve_floor_position = cls.mixing_valve_floor_position
                    if mixing_valve_floor_position == 0:
                        await set_mixing_valve(-150)
                        mixing_valve_floor_ts = time.monotonic()
                await asyncio.sleep(15)

                if mixing_valve_floor_ts < time.monotonic() - 14400:
                    await set_mixing_valve(-150)
                    mixing_valve_floor_position = 0
            except Exception as e:
                print(f'\x1b[31m#{__name__}:458# {type(e).__name__} "{e}"\x1b[0m')

    @classmethod
    async def check_overheated_floor(cls):
        c = 0
        while True:
            c += 1
            floor_temp_sensor = cls.ds.get_valid_sensor('floor_temp_sensor')
            cls.mixing_valve_status["debug"] = f"#:467:{c}# check_overheated_floor {floor_temp_sensor=}"
            if floor_temp_sensor and floor_temp_sensor < 40:
                break
            cls.mixing_valve_floor_position = 0
            print(f">>:489# {cls.mixing_valve_floor_position=} OFF")
            cls.mixing_valve_status["overheated floor"] = True
            await asyncio.sleep(12)
        cls.mixing_valve_status["overheated floor"] = False

    @classmethod
    async def inside_temp(cls):
        print(f'\x1b[36m#{__name__}:462# inside_temp\x1b[0m')

        cls.mixing_valve_floor_position = 0
        print(f">>:503# {cls.mixing_valve_floor_position=} OFF")
        taskvalve = asyncio.create_task(cls.mixing_valve_ctrl())
        taskave = asyncio.create_task(cls.ave())
        taskstate = asyncio.create_task(cls.valve_state())
        while True:
            print(f'\x1b[36m#{__name__}:470# inside_temp\x1b[0m')

            try:
                await asyncio.sleep(12)
                inside_temp_sensor = cls.ds.get_valid_sensor('inside_temp_sensor')
                inside_temp_setpoint = cls.ds.get_value_setpoint('inside_temp_setpoint')
                print(f'#{__name__}:490# {inside_temp_sensor=} {inside_temp_setpoint=}')

                # wyłączenie grzania
                if inside_temp_sensor is None:  # zawsze włączona or inside_temp_sensor > inside_temp_setpoint:
                    print(f'#{__name__}:482# {inside_temp_sensor=} {inside_temp_setpoint=}')
                    cls.pump_floor = False
                    cls.mixing_valve_floor_position = 0
                    print(f">>OFF:520 {cls.mixing_valve_floor_position=}")
                    continue

                # włącz pompę
                cls.pump_floor = True

                # odczekaj być może czujnik nagrzany, lub pompa nie włączyła się B1
                await cls.check_overheated_floor()

                inside_hour_last = ave_temps.sensors['inside_temp_sensor'].get_hour(-1)
                inside_qtr_last = ave_temps.sensors['inside_temp_sensor'].get_qtr(-1)

                if None in [inside_hour_last, inside_qtr_last]:
                    cls.mixing_valve_status["debug"] = f"#:513# None >> {inside_hour_last=} {inside_qtr_last=}"
                    continue

                if (inside_temp_setpoint - 0.1) <= inside_qtr_last <= (inside_temp_setpoint + 0.1):
                    cls.mixing_valve_status["temperature_is_stable"] = True
                    await asyncio.sleep(60)
                    continue

                if (inside_temp_setpoint - 0.1) <= inside_hour_last <= (inside_temp_setpoint + 0.1):
                    cls.mixing_valve_status["temperature_is_stable"] = True
                    await asyncio.sleep(60)
                    continue

                inside_temp_day = ave_temps.sensors['inside_temp_sensor'].get_day()
                if inside_temp_day is not None:
                    # jeżeli średnia dobowa mieści się to możemy skorzystać ze średniej floor_temp_day
                    if (inside_temp_setpoint - 0.9) <= inside_temp_day <= (inside_temp_setpoint + 0.9):
                        if inside_qtr_last < (inside_temp_setpoint - 0.2):
                            cls.mixing_valve_floor_position += 1
                            if cls.mixing_valve_floor_position > 100:
                                cls.mixing_valve_floor_position = 100
                            await asyncio.sleep(300)
                            continue
                        elif inside_qtr_last > (inside_temp_setpoint + 0.2):
                            cls.mixing_valve_floor_position -= 1
                            if cls.mixing_valve_floor_position < 0:
                                cls.mixing_valve_floor_position = 0
                            await asyncio.sleep(300)
                            continue

                        await asyncio.sleep(60)
                        continue
                    if (inside_temp_setpoint - 1.9) <= inside_temp_day <= (inside_temp_setpoint + 1.9):
                        if inside_qtr_last < (inside_temp_setpoint - 0.2):
                            cls.mixing_valve_floor_position += 3
                            if cls.mixing_valve_floor_position > 100:
                                cls.mixing_valve_floor_position = 100
                            await asyncio.sleep(300)
                            continue
                        elif inside_qtr_last > (inside_temp_setpoint + 0.2):
                            cls.mixing_valve_floor_position -= 3
                            if cls.mixing_valve_floor_position < 0:
                                cls.mixing_valve_floor_position = 0
                            await asyncio.sleep(300)
                            continue

                        await asyncio.sleep(60)
                        continue

                cls.mixing_valve_status["temperature_is_stable"] = False

                delta_inside = inside_qtr_last - inside_hour_last
                cls.mixing_valve_status["inside_qtr_last"] = inside_qtr_last
                cls.mixing_valve_status["inside_hour_last"] = inside_hour_last
                cls.mixing_valve_status["delta_inside"] = delta_inside
                if delta_inside > 0:
                    # temperatura rośnie
                    # jak bardzo, jeśli słabo to zwiększamy.
                    if delta_inside < (inside_temp_setpoint - inside_qtr_last) / 5:
                        cls.mixing_valve_floor_position = int(1.2 * cls.mixing_valve_floor_position)
                        if cls.mixing_valve_floor_position > 100:
                            cls.mixing_valve_floor_position = 100
                        print(f">>565:# {cls.mixing_valve_floor_position=}")
                        for x in range(15):
                            inside_qtr_last = ave_temps.sensors['inside_temp_sensor'].get_qtr(-1)
                            inside_min_last = ave_temps.sensors['inside_temp_sensor'].get_min(-1)
                            delta_inside = inside_min_last - inside_qtr_last
                            cls.mixing_valve_status["delta_inside"] = delta_inside
                            if delta_inside < 0:
                                break
                            inside_temp_sensor = cls.ds.get_valid_sensor('inside_temp_sensor')
                            cls.mixing_valve_status["inside_temp_sensor"] = inside_temp_sensor
                            floor_temp_sensor = cls.ds.get_valid_sensor('floor_temp_sensor')
                            cls.mixing_valve_status["floor_temp_sensor"] = floor_temp_sensor
                            cls.mixing_valve_status["debug"] = f"#:546:{x}# await upper {inside_qtr_last=} {inside_min_last=}"
                            await asyncio.sleep(60)
                    continue
                dq = inside_temp_setpoint - inside_qtr_last  # 21.2-21 = 0.2
                dh = inside_temp_setpoint - inside_hour_last  # 21.2-20.8 = 0.4
                if (dh-dq) > 0:
                    if 0 < dq < 0.1:
                        cls.mixing_valve_floor_position -= 10
                    elif 0 < dq < 0.2:
                        cls.mixing_valve_floor_position -= 8
                    elif 0 < dq < 0.5:
                        cls.mixing_valve_floor_position -= 5
                    elif 0 < dq < 0.9:
                        cls.mixing_valve_floor_position -= 2

                    if cls.mixing_valve_floor_position < 0:
                        cls.mixing_valve_floor_position = 0
                # maleje albo jest stała wiec trzeba podnieść wartość 0 1 i poczekać 1 minutę

                print(f">>#:581# {cls.mixing_valve_floor_position=}")
                cls.mixing_valve_floor_position += 10
                if cls.mixing_valve_floor_position > 100:
                    cls.mixing_valve_floor_position = 100
                print(f">>#:583# {cls.mixing_valve_floor_position=}")
                for x in range(15):
                    inside_qtr_last = ave_temps.sensors['inside_temp_sensor'].get_qtr(-1)
                    inside_min_last = ave_temps.sensors['inside_temp_sensor'].get_min(-1)
                    delta_inside = inside_min_last - inside_qtr_last
                    cls.mixing_valve_status["delta_inside"] = delta_inside

                    inside_temp_sensor = cls.ds.get_valid_sensor('inside_temp_sensor')
                    cls.mixing_valve_status["inside_temp_sensor"] = inside_temp_sensor
                    floor_temp_sensor = cls.ds.get_valid_sensor('floor_temp_sensor')
                    cls.mixing_valve_status["floor_temp_sensor"] = floor_temp_sensor
                    cls.mixing_valve_status["debug"] = f"#:566:{x}# await lower {inside_qtr_last=} {inside_min_last=}"
                    await asyncio.sleep(60)

                print(f'#{__name__}:570# {floor_temp_sensor=}')
            except Exception as e:
                print(f"\x1b[31mERROR:261 {type(e).__name__} {e}\x1b[0m")
                cls.mixing_valve_status["debug"] = f"#:566# ERROR {type(e).__name__} {e}"


async def temp_csv(ds):
    await asyncio.sleep(15)
    ts_hour = int(time.time()) // 60
    while True:
        try:
            ts_min = int(time.time()) // 60
            _ts_hour = ts_min // 60
            for sensor in ave_temps.sensors:
                value = ds.get_valid_sensor(sensor)
                ave_temps.sensors[sensor].add(ts_min, value)
            if ts_hour != _ts_hour:
                buff = [datetime.datetime.now().replace(second=0, microsecond=0).isoformat()]
                for sensor in ave_temps.sensors:
                    buff.append(ave_temps.sensors[sensor].get_hour(-1))
                await temp_log.update(*buff)
                ts_hour = _ts_hour
        except Exception as e:
            print(f"\x1b[31m#ERROR:596# {type(e).__name__} {e}\x1b[0m")
        await asyncio.sleep(12)
