import json
import pika

RMQ_HOSTS = [
    "100.94.40.126",  # RMQ3 - Meek
    "100.65.228.57",  # RMQ2 - Amaan
    "100.114.37.13",  # RMQ1 - Daniel
]

RMQ_PORT = 5672
RMQ_USER = "music"
RMQ_PASS = "music123"

REGISTER_RESPONSE_QUEUE = "auth.register.bedb_to_fe"
LOGIN_RESPONSE_QUEUE = "auth.login.bedb_to_fe"


def get_connection():
    credentials = pika.PlainCredentials(RMQ_USER, RMQ_PASS)
    last_error = None

    for host in RMQ_HOSTS:
        try:
            print(f"[fe_listener] Trying RMQ node: {host}")
            params = pika.ConnectionParameters(
                host=host,
                port=RMQ_PORT,
                credentials=credentials,
                heartbeat=30,
                blocked_connection_timeout=30
            )
            return pika.BlockingConnection(params)
        except Exception as e:
            print(f"[fe_listener] Failed RMQ node {host}: {e}")
            last_error = e

    raise last_error


def declare_queue(channel, queue_name):
    channel.queue_declare(
        queue=queue_name,
        durable=True,
        arguments={"x-queue-type": "quorum"}
    )


def on_response(ch, method, props, body):
    print("\n[FE Listener] Response received")
    print("[FE Listener] Queue:", method.routing_key)
    print("[FE Listener] Correlation ID:", props.correlation_id)

    try:
        decoded_body = body.decode("utf-8")
        print("[FE Listener] Body:", decoded_body)
    except Exception:
        print("[FE Listener] Body could not be decoded.")

    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    connection = get_connection()
    channel = connection.channel()

    declare_queue(channel, REGISTER_RESPONSE_QUEUE)
    declare_queue(channel, LOGIN_RESPONSE_QUEUE)

    channel.basic_qos(prefetch_count=1)

    channel.basic_consume(
        queue=REGISTER_RESPONSE_QUEUE,
        on_message_callback=on_response
    )

    channel.basic_consume(
        queue=LOGIN_RESPONSE_QUEUE,
        on_message_callback=on_response
    )

    print("[FE Listener] Waiting for final FE responses...")

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("\n[FE Listener] Shutting down...")
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()