# main.py
import asyncio
import logging

import config
from manager import DataShadow
from mqtt_controller import MQTTController
from relay_client import GatewayRelay
from heating import Heating, temp_csv

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("main")


def build_service(cfg=config):
    """Składa usługę z konfiguracji, nie startując jeszcze sieci - ułatwia
    sprawdzenie samego spięcia (topici, kanały) bez brokera i bez gatewaya."""
    ds = DataShadow()
    mqtt = MQTTController(ds, host=cfg.MQTT_BROKER_HOST, port=cfg.MQTT_BROKER_PORT)
    relays = GatewayRelay(
        publish=mqtt.publish,
        topic_root=cfg.RELAY_TOPIC_ROOT,
        module=cfg.RELAY_MODULE,
        service=cfg.SERVICE_NAME,
        priority=cfg.LEASE_PRIORITY,
    )
    return ds, mqtt, relays


async def main():
    ds, mqtt, relays = build_service()
    mqtt.start()

    Heating.init(ds, mqtt.publish, relays, is_connected=lambda: mqtt.client.is_connected())

    LOG.info("Start: moduł gatewaya '%s', broker %s:%s", config.RELAY_MODULE,
             config.MQTT_BROKER_HOST, config.MQTT_BROKER_PORT)

    asyncio.create_task(temp_csv(ds))
    asyncio.create_task(Heating.fan_keepalive())
    if config.PUMP_BOILER_CTRL_ENABLED:
        asyncio.create_task(Heating.pump_boiler_ctrl())

    while True:
        await Heating.main()
        await asyncio.sleep(15)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
