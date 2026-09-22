import paho.mqtt.client as mqtt
import json


class MqttReporter:
    def __init__(self, broker_host="localhost", broker_port=1883, base_topic="Station/3"):
        self.base_topic = base_topic
        self.client = mqtt.Client()
        self.client.connect(broker_host, broker_port, keepalive=60)
        self.client.loop_start()  # läuft im Hintergrund, kümmert sich um Netzwerk-Kram

    def report_status(self, status: str):
        """z.B. 'busy', 'idle'"""
        self.client.publish(f"{self.base_topic}/status", status, retain=True)

    def report_guess(self, guessed_code: list):
        # Als JSON, falls du strukturierte Daten senden willst
        payload = json.dumps({"guess": guessed_code})
        self.client.publish(f"{self.base_topic}/guess", payload)

    def report_answer(self, correct_code: list):
        payload = json.dumps({"answer": correct_code})
        self.client.publish(f"{self.base_topic}/answer", payload)

    def report_feedback(self, feedback: int):
        self.client.publish(f"{self.base_topic}/feedback", feedback, retain=True)

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()