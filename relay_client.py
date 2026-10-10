# relay_client.py
"""Cienki klient waveshare-mqtt-gateway, adresowany numerem kanału (nie nazwą
grzałki) - tak samo jak stary bezpośredni sterownik Realy30CH, żeby heating.py
mogło podmienić `cls.relays` bez zmiany sposobu wywołań.

heating.py sam pamięta, czego chce (feeding_timestamp, pump_floor,
mixing_valve_floor_position) niezależnie od potwierdzenia ze sprzętu, więc tu
celowo nie ma modelu "energized"/retained-status jak w cwu-controller -
byłaby to niewykorzystana złożoność.
"""
import json
import logging

LOG = logging.getLogger("relay_client")


class GatewayRelay:
    def __init__(self, publish, topic_root, module, service, priority=10):
        self.publish = publish
        self.topic_root = topic_root
        self.module = module
        self.service = service
        self.priority = priority

    def cmd_topic(self, channel):
        return f"{self.topic_root}/{self.module}/ch{channel}/cmd/{self.service}"

    def _send(self, channel, body):
        topic = self.cmd_topic(channel)
        info = self.publish(topic, json.dumps(body), qos=1)
        rc = getattr(info, "rc", None)
        if rc not in (None, 0):
            LOG.warning("Publikacja komendy przekaźnika nieudana (rc=%s): %s %s", rc, topic, body)
        return info

    async def relay_on(self, channel, ttl=None):
        body = {"cmd": "on", "priority": self.priority}
        if ttl is not None:
            body["ttl"] = ttl
        return self._send(channel, body)

    async def relay_off(self, channel, ttl=None):
        body = {"cmd": "off", "priority": self.priority}
        if ttl is not None:
            body["ttl"] = ttl
        return self._send(channel, body)

    async def relay_flash_on(self, channel, timeout=1.0):
        body = {"cmd": "flash_on", "duration": timeout, "priority": self.priority}
        return self._send(channel, body)

    async def relay_flash_off(self, channel, timeout=1.0):
        """Nieużywane dzisiaj. UWAGA: to nie jest szybkie wyłączenie - to impuls
        odwrotny (rozwiera cewkę na `timeout`, po czym ją zwiera i tak zostawia),
        czyli zarazem roszczenie "trzymaj on" na gatewayu. Patrz README gatewaya."""
        body = {"cmd": "flash_off", "duration": timeout, "priority": self.priority}
        return self._send(channel, body)

# end.
