import time
import json
import logging

class ServiceHealthTracker:
    def __init__(self, mqtt_client, service_name):
        self.client = mqtt_client
        self.service_name = service_name
        self.state_topic = f"home/service/{service_name}/status"
        self.last_update = 0
        self.update_interval = 30  # Only push a heartbeat every 30 seconds to prevent MQTT spam
        
        # Publish Home Assistant Auto-Discovery for the Health Sensor
        discovery_topic = f"homeassistant/sensor/{service_name}_health/config"
        discovery_payload = {
            "name": f"{service_name.replace('_', ' ').title()} Status",
            "state_topic": self.state_topic,
            "value_template": "{{ value_json.status }}",
            "unique_id": f"{service_name}_health_watchdog",
            "device": {
                "identifiers": ["labpulse_core_services"],
                "name": "LabPulse Background Services"
            },
            "json_attributes_topic": self.state_topic
        }
        self.client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)

    def update(self):
        """Pings Home Assistant to prove the script hasn't crashed."""
        current_time = time.time()
        
        # Only broadcast if 30 seconds have passed
        if current_time - self.last_update >= self.update_interval:
            payload = {
                "status": "Online",
                "last_seen": time.strftime('%Y-%m-%d %H:%M:%S')
            }
            self.client.publish(self.state_topic, json.dumps(payload), retain=True)
            self.last_update = current_time
