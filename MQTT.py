import paho.mqtt.client as mqtt
import json


class MqttReporter:
    """Schickt Spielereignisse an den Broker. Ist der Broker nicht
    erreichbar, wird MQTT einfach deaktiviert und alle report_*-Aufrufe
    tun nichts - das Spiel läuft trotzdem weiter."""

    def __init__(self, broker_host="localhost", broker_port=1883, base_topic="Station/3"):
        self.base_topic = base_topic
        self.enabled = False
        self.client = None
        try:
            # paho-mqtt 2.x will die Callback-API-Version explizit haben
            if hasattr(mqtt, "CallbackAPIVersion"):
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            else:
                self.client = mqtt.Client()
            self.client.connect(broker_host, broker_port, keepalive=60)
            self.client.loop_start()  # läuft im Hintergrund, kümmert sich um Netzwerk-Kram
            self.enabled = True
            print(f"MQTT verbunden mit {broker_host}:{broker_port}")
        except Exception as e:
            print(f"MQTT nicht verfügbar ({e}) - MQTT deaktiviert")
            self.client = None

    def _publish(self, topic: str, payload, retain=False):
        if not self.enabled:
            return
        try:
            self.client.publish(f"{self.base_topic}/{topic}", payload, retain=retain)
        except Exception as e:
            print(f"MQTT publish fehlgeschlagen: {e}")

    def report_status(self, status: str):
        """z.B. 'busy', 'idle'"""
        self._publish("status", status, retain=True)

    def report_guess(self, guessed_code: list):
        # Als JSON, falls du strukturierte Daten senden willst
        self._publish("guess", json.dumps({"guess": guessed_code}))

    def report_answer(self, correct_code: list):
        self._publish("answer", json.dumps({"answer": correct_code}))

    def report_feedback(self, feedback: int):
        self._publish("feedback", feedback, retain=True)

    def close(self):
        if not self.enabled:
            return
        self.client.loop_stop()
        self.client.disconnect()
