# mqtt_controller.py
import json
import threading
import time
import logging
import paho.mqtt.client as mqtt
import platform


log = LOG = logging.getLogger("mqtt_controller")

class MQTTController:
    """
    MQTT in a separate thread using paho-mqtt.
    - reconnect loop
    - on_message updates DataStore via provided manager
    """
    def __init__(self, datastore, host="localhost", port=1883):
        self.ds = datastore
        self.host = host
        self.port = port
        self._stop = threading.Event()

        # Using callback API VERSION2 as you wanted, and MQTT v3.1.1

        if platform.system() == "Linux":
            client_id = "heating-service"
        else:
            client_id = "heating-debug"

        self.client = mqtt.Client(client_id=client_id,
                        protocol=mqtt.MQTTv311,
                        callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self._thread = threading.Thread(target=self._run_loop, daemon=True)

    # ---------------- callbacks ----------------
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        print(f"[MQTT] Connected rc={rc}")
        # (re)subscribe
        if rc == 0:
            client.subscribe("cave/sensors/temperature/#")
            client.subscribe("cave/heating/setpoints/#")
            client.subscribe("cave/heating/commands/#")
            client.subscribe("cave/sensors/airco2/#")
            client.subscribe("cave/sensors/humidity/#")
        else:
            print(f"[MQTT] Connection failed (rc={rc})")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties=None):
        print(f"[MQTT] Disconnected rc={reason_code}")

    def _on_message(self, client, userdata, message, properties=None):
        topic = message.topic
        payload = message.payload.decode(errors="ignore").strip()
        # try JSON -> number -> string
        value = None
        try:
            if payload.startswith("{") or payload.startswith("["):
                value = json.loads(payload).get('value', None)
            else:
                # try float or int
                if '.' in payload:
                    value = float(payload)
                else:
                    value = int(payload)
        except Exception:
            value = payload

        parts = topic.split("/")
        # topic formats:
        # cave/sensors/temperature/<name>
        # cave/heating/setpoints/<name>
        # cave/heating/commands/<cmd>
        if len(parts) >= 4 and parts[0] == "cave":
            if parts[1] == "sensors" and parts[2] in ["temperature", "airco2", "humidity"]:
                name = parts[3]
                try:
                    self.ds.update_sensor(name, float(value))
                except Exception:
                    LOG.exception("Invalid sensor value for %s: %r", name, value)
            elif parts[1] == "heating" and parts[2] == "setpoints":
                name = parts[3]
                try:
                    if value != "":
                        self.ds.update_setpoint(name, float(value))
                except Exception:
                    LOG.exception("Invalid setpoint for %s: %r", name, value)
            elif parts[1] == "heating" and parts[2] == "commands":
                cmd = parts[3]
                print("Received command %s : %r", cmd, value)
                # TODO: implement command callbacks if needed

    def publish(self, topic, msg, qos=0, retain=False):
        return self.client.publish(topic, msg, qos=qos, retain=retain)

    # ---------------- thread loop ----------------
    def start(self):
        if not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            self.client.disconnect()
            self.client.loop_stop()
        except Exception:
            pass

    def _run_loop(self):
        print(f"Connecting to MQTT {self.host=} {self.port=}")
        self.client.connect(self.host, self.port, keepalive=30)
        try:
            self.client.loop_forever(retry_first_connection=True)
        except Exception as e:
            LOG.exception("MQTT loop error: %s", e)

# end.
