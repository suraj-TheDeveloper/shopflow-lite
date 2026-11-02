from confluent_kafka.admin import AdminClient, NewTopic

admin = AdminClient({"bootstrap.servers": "localhost:9092"})

futures = admin.create_topics([
    NewTopic("shopflow-events", num_partitions=3, replication_factor=1),
    NewTopic("shopflow-events-dlq", num_partitions=3, replication_factor=1),
])

for topic, f in futures.items():
    try:
        f.result()
        print("created", topic)
    except Exception as e:
        print(topic, "->", e)   # "already exists" is fine