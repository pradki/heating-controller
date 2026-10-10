# tests/test_relay_client.py - komendy do gatewaya z GatewayRelay
import asyncio
import json

from fakes import build, check, done

TOPIC_FAN = "cave/relay/relay_heating/ch26/cmd/heating_service"


def run(coro):
    return asyncio.run(coro)


pub, relay = build()

check("topic komendy adresowany numerem kanału", relay.cmd_topic(26) == TOPIC_FAN)

# --- flash_on: impuls sprzętowy, czas trwania wymagany ---
run(relay.relay_flash_on(26, timeout=30))
topic, payload, qos, retain, rc = pub.last(TOPIC_FAN)
check("flash_on trafia na właściwy topic", topic == TOPIC_FAN)
check("flash_on niesie cmd/duration/priority",
      json.loads(payload) == {"cmd": "flash_on", "duration": 30, "priority": 10})
check("komendy przekaźnika idą z QoS 1 (nie giną cicho przy rozłączeniu)", qos == 1)
check("komenda nie jest retained", retain is False)

# --- on/off: jawny ttl, gdy podany ---
pub.clear()
run(relay.relay_on(1, ttl=1800))
check("on z jawnym ttl",
      json.loads(pub.last("cave/relay/relay_heating/ch1/cmd/heating_service")[1])
      == {"cmd": "on", "priority": 10, "ttl": 1800})

pub.clear()
run(relay.relay_off(1))
check("off bez ttl nie dokłada pola ttl (gateway użyje DEFAULT_LEASE_TTL)",
      json.loads(pub.last("cave/relay/relay_heating/ch1/cmd/heating_service")[1])
      == {"cmd": "off", "priority": 10})

# --- flash_off: zachowany dla parytetu API, ale nieużywany przez heating.py ---
pub.clear()
run(relay.relay_flash_off(5, timeout=3))
check("flash_off niesie cmd/duration/priority",
      json.loads(pub.last("cave/relay/relay_heating/ch5/cmd/heating_service")[1])
      == {"cmd": "flash_off", "duration": 3, "priority": 10})

# --- publikacja nieudana (np. broker rozłączony) tylko loguje, nie wywraca wywołania ---
pub.clear()
pub.fail_next = True
run(relay.relay_flash_on(26, timeout=30))
check("nieudana publikacja nie rzuca wyjątku (tylko ostrzeżenie w logu)",
      pub.last(TOPIC_FAN)[4] == 4)

done()
