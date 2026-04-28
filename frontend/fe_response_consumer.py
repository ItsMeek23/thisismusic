import json
import pika
import time

RMQ_HOSTS = [
    "100.94.40.126",  # RMQ3 - Meek
    "100.65.228.57",  # RMQ2 - Amaan
    "100.114.37.13",  # RMQ1 - Daniel
]

RMQ_PORT = 5672
RMQ_USER = "music"
RMQ_PASS = "music123"


def get_connection():
    credentials = pika.PlainCredentials(RMQ_USER, RMQ_PASS)
    last_error = None

    for host in RMQ_HOSTS:
        try:
            print(f"[FE Consumer] Trying RMQ node: {host}")
            params = pika.ConnectionParameters(
                host=host,
                port=RMQ_PORT,
                credentials=credentials,
                heartbeat=30,
                blocked_connection_timeout=30,
                connection_attempts=1,
                retry_delay=0
            )
            return pika.BlockingConnection(params)
        except Exception as e:
            print(f"[FE Consumer] Failed RMQ node {host}: {e}")
            last_error = e

    raise last_error


def declare_quorum_queue(channel, queue_name):
    channel.queue_declare(
        queue=queue_name,
        durable=True,
        arguments={"x-queue-type": "quorum"}
    )


def wait_for_response(queue_name, correlation_id, timeout=10):
    connection = get_connection()
    channel = connection.channel()

    declare_quorum_queue(channel, queue_name)

    print(f"[FE Consumer] Waiting on queue: {queue_name}")
    print(f"[FE Consumer] Looking for correlation ID: {correlation_id}")

    start_time = time.time()

    while time.time() - start_time < timeout:
        method_frame, header_frame, body = channel.basic_get(
            queue=queue_name,
            auto_ack=False
        )

        if method_frame:
            try:
                decoded = json.loads(body.decode("utf-8"))

                prop_correlation_id = getattr(header_frame, "correlation_id", None)
                body_correlation_id = decoded.get("correlation_id")

                print(f"[FE Consumer] Message received from queue: {queue_name}")
                print(f"[FE Consumer] Property correlation ID: {prop_correlation_id}")
                print(f"[FE Consumer] Body correlation ID: {body_correlation_id}")

                if prop_correlation_id == correlation_id or body_correlation_id == correlation_id:
                    channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                    connection.close()
                    print(f"[FE Consumer] Matching response received: {decoded}")
                    return decoded

                # Not our message → put it back
                channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=True)

            except Exception as e:
                print(f"[FE Consumer] Invalid JSON response from backend: {e}")
                channel.basic_ack(delivery_tag=method_frame.delivery_tag)

        time.sleep(0.05)

    connection.close()
    print("[FE Consumer] Timeout waiting for response")

    return {
        "status": "fail",
        "message": "Backend timeout or no response received"
    }