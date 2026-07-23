import paho.mqtt.client as mqtt
import time

BROKER = "localhost"
PORT = 1883
TOPIC_FILTER = "homeassistant/#"
discovery_topics = []

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(TOPIC_FILTER)

def on_message(client, userdata, msg):
    if msg.retain and msg.topic.endswith("/config"):
        discovery_topics.append(msg.topic)

def list_and_clear():
    print("\n🔍 Scanning retained MQTT discovery topics...\n")
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT, 60)
    client.loop_start()

    time.sleep(2)  # wait for retained messages to arrive
    client.loop_stop()

    if not discovery_topics:
        print("00 No retained discovery topics found.")
        return

    print("-- Retained MQTT discovery topics found:\n")
    for i, topic in enumerate(discovery_topics, start=1):
        print(f"{i}. {topic}")

    print("\nOptions:")
    print("  [a] Delete ALL")
    print("  [1 3 5] Delete specific entries (space-separated numbers)")
    print("  [q] Quit without deleting")

    choice = input("\nEnter your choice: ").strip()

    client.connect(BROKER, PORT, 60)
    if choice.lower() == 'a':
        for topic in discovery_topics:
            client.publish(topic, payload=None, retain=True)
            print(f"[]  Deleted: {topic}")
    elif choice.lower() == 'q':
        print("XX No topics deleted.")
    else:
        try:
            indexes = list(map(int, choice.split()))
            for i in indexes:
                topic = discovery_topics[i - 1]
                client.publish(topic, payload=None, retain=True)
                print(f"[]  Deleted: {topic}")
        except Exception as e:
            print(f"!! Invalid selection: {e}")

    print("\n00 Done. You may need to restart Home Assistant to see changes.")

if __name__ == "__main__":
    list_and_clear()
