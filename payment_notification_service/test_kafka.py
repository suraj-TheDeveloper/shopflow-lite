import json
from confluent_kafka import Producer, Consumer

p = Producer({"bootstrap.servers": "localhost:9092", "acks": "all"})
p.produce("shopflow-events", key="1",
          value=json.dumps({"event_id": "test-1", "event_type": "order.created",
                            "data": {"order_id": 1, "user_id": 1, "amount": "100"}}))
p.flush(30)
print("sent")

c = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "test-group",
    "enable.auto.commit": False,
    "auto.offset.reset": "earliest",
})
c.subscribe(["shopflow-events"])
for _ in range(180):                      # wait up to ~30s; first poll is slow
    msg = c.poll(1.0)
    if msg and not msg.error():
        print("received:", msg.value().decode(), "partition", msg.partition(), "offset", msg.offset())
        c.commit(msg)
        break
else:
    print("nothing received")
c.close()