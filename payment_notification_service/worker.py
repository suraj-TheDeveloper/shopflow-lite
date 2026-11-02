import json
from confluent_kafka import Consumer, Producer, TopicPartition
from database import sessionLocal, engine
from models import Base, Notification

BOOTSTRAP = "localhost:9092"
TOPIC = "shopflow-events"
DLQ_TOPIC = "shopflow-events-dlq"
MAX_RETRIES = 3

Base.metadata.create_all(engine)

# ---------- handlers ----------
def _save_notification(event, user_id, ntype, message):
    db = sessionLocal()
    try:
        if db.query(Notification).filter_by(event_id=event["event_id"]).first():
            return                                   # already processed (redelivery)
        db.add(Notification(user_id=user_id, type=ntype, message=message,
                            event_id=event["event_id"]))
        db.commit()
    finally:
        db.close()

def handle_order_created(event):
    d = event["data"]
    _save_notification(event, d["user_id"], "order_created",
                       f"Your order #{d['order_id']} was placed. Total: {d['amount']}.")

def handle_payment_success(event):
    d = event["data"]
    _save_notification(event, d["user_id"], "payment_success",
                       f"Payment of {d['amount']} received for order #{d['order_id']}.")

def handle_payment_failed(event):
    d = event["data"]
    _save_notification(event, d["user_id"], "payment_failed",
                       f"Payment failed for order #{d['order_id']}. Please try again.")

# ---------- dictionary dispatch ----------
HANDLERS = {
    "order.created": handle_order_created,
    "payment.success": handle_payment_success,
    "payment.failed": handle_payment_failed,
}

# ---------- kafka ----------
consumer = Consumer({
    "bootstrap.servers": BOOTSTRAP,
    "group.id": "notification-worker",
    "enable.auto.commit": False,          # manual offsets
    "auto.offset.reset": "earliest",
})
consumer.subscribe([TOPIC])
dlq_producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all"})

def send_to_dlq(msg, reason):
    dlq_producer.produce(DLQ_TOPIC, key=msg.key(), value=msg.value(),
                         headers=[("error", reason.encode())])
    dlq_producer.flush()

retries = {}   # (partition, offset) -> attempts

print("worker started, waiting for events...")
try:
    while True:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            print("consumer error:", msg.error())
            continue

        # 1. Parse and route. A malformed message is a poison pill -> DLQ
        try:
            event = json.loads(msg.value())
            handler = HANDLERS[event["event_type"]]
            event["event_id"], event["data"]          # required fields must exist
        except (ValueError, KeyError, TypeError) as e:
            print("poison pill -> DLQ:", e)
            send_to_dlq(msg, f"malformed: {e!r}")
            consumer.commit(msg, asynchronous=False)  # commit so it doesn't block the partition
            continue

        # 2. Handle. Commit only after the DB transaction succeeded
        try:
            handler(event)
            consumer.commit(msg, asynchronous=False)
            print(f"handled {event['event_type']} at offset {msg.offset()}")
        except Exception as e:
            k = (msg.partition(), msg.offset())
            retries[k] = retries.get(k, 0) + 1
            if retries[k] >= MAX_RETRIES:
                print("giving up -> DLQ:", e)
                send_to_dlq(msg, f"failed after retries: {e!r}")
                consumer.commit(msg, asynchronous=False)
                retries.pop(k, None)
            else:
                print(f"handler failed ({retries[k]}/{MAX_RETRIES}), retrying: {e}")
                # no commit: rewind so this message is delivered again
                consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
except KeyboardInterrupt:
    pass
finally:
    consumer.close()