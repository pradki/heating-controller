# manager.py
import time
from typing import Optional
import threading
import shadow_vault


DEFAULT_SENSOR_TTL = 15 * 60  # 15 minutes


class SensorValue:
    """Dane z czujnika — mają TTL (wygasają)."""
    def __init__(self, value: float, ttl: int = DEFAULT_SENSOR_TTL):
        self.value = value
        self.ts = time.time()
        self.ttl = ttl

    def update(self, value: float):
        self.value = value
        self.ts = time.time()

    def age(self) -> float:
        return time.time() - self.ts

    def is_valid(self) -> bool:
        return (time.time() - self.ts) <= self.ttl


class Setpoint:
    """Wartość zadana — nie wygasa (dopóki ktoś nie zmieni jej przez MQTT)."""
    def __init__(self, value: float):
        self.value = value

    def update(self, value: float):
        self.value = value


class TimedValue:
    """Przechowuje wartość i czas ostatniej aktualizacji."""
    def __init__(self, value=None, ttl=None):
        self.value = value
        self.timestamp = time.monotonic()
        self.ttl = ttl  # None dla wartości trwałych (np. setpointy)

    def update(self, value):
        self.value = value
        self.timestamp = time.monotonic()

    def is_valid(self):
        if self.ttl is None:
            return True
        return (time.monotonic() - self.timestamp) < self.ttl


class DataShadow:
    """Wspólny store dla sensorów i setpointów. Thread-safe dla MQTT thread."""
    def __init__(self):
        self._lock = threading.Lock()

    # --- sensors ---
    def update_sensor(self, name: str, value: float):
        with self._lock:
            if not name.endswith('_sensor'):
                name = f'{name}_sensor'

            if name in shadow_vault.PARAMS:
                shadow_vault.PARAMS[name]['value'] = value
                shadow_vault.PARAMS[name]['timestamp'] = time.monotonic()

    def get_sensor(self, name: str) -> dict:
        with self._lock:
            if not name.endswith('_sensor'):
                name = f'{name}_sensor'

            return shadow_vault.PARAMS.get(name)

    def get_valid_sensor(self, name: str) -> dict:
        with self._lock:
            if not name.endswith('_sensor'):
                name = f'{name}_sensor'

            return shadow_vault.get_valid_sensor(name)

    # --- setpoints ---
    def update_setpoint(self, name: str, value: float):
        with self._lock:
            if not name.endswith('_setpoint'):
                name = f'{name}_setpoint'

            monotonic = time.monotonic()
            shadow_vault.update_from_broker(name, value, monotonic)

    def get_setpoint(self, name: str) -> dict:
        with self._lock:
            if not name.endswith('_setpoint'):
                name = f'{name}_setpoint'

            return shadow_vault.PARAMS.get(name)

    def get_value_setpoint(self, name: str) -> dict:
        with self._lock:
            if not name.endswith('_setpoint'):
                name = f'{name}_setpoint'

            return shadow_vault.if_null_then_conditional_default(name)

    # helper
    def has_setpoint(self, name: str) -> bool:
        with self._lock:
            return name in self._setpoints


# end.
