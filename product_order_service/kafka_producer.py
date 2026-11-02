import json, uuid
from confluent_kafka import Producer

TOPIC = "shopflow-events"

producer = Producer({
    "bootstrap.servers": "localhost:9092",
    "acks": "all",
    "enable.idempotence": True,
})

def _on_delivery(err, msg):
    if err:
        print(f"[kafka] delivery FAILED: {err}")
    else:
        print(f"[kafka] delivered {msg.topic()}[{msg.partition()}]@{msg.offset()}")

def publish_event(event_type: str, key: str, data: dict):
    event = {"event_id": str(uuid.uuid4()), "event_type": event_type, "data": data}
    try:
        producer.produce(TOPIC, key=key, value=json.dumps(event), callback=_on_delivery)
        producer.poll(0)       # serves callbacks, never blocks the request
    except Exception as e:
        print(f"[kafka] could not enqueue {event_type}: {e}")   # don't fail the HTTP request