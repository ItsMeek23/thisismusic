import json
import uuid
import pika

RMQ_HOSTS = [
    "100.114.37.13",  # RMQ1 - Daniel
    "100.65.228.57",  # RMQ2 - Amaan
    "100.94.40.126",  # RMQ3 - Meek
]
RMQ_PORT = 5672
RMQ_USER = "music"
RMQ_PASS = "music123"

HISTORY_ADD_REQUEST_QUEUE = "history.add.fe_to_befe"
HISTORY_GET_REQUEST_QUEUE = "history.get.fe_to_befe"
HISTORY_CLEAR_REQUEST_QUEUE = "history.clear.fe_to_befe"

HISTORY_ADD_RESPONSE_QUEUE = "history.add.bedb_to_fe"
HISTORY_GET_RESPONSE_QUEUE = "history.get.bedb_to_fe"
HISTORY_CLEAR_RESPONSE_QUEUE = "history.clear.bedb_to_fe"


def get_connection():
    credentials = pika.PlainCredentials(RMQ_USER, RMQ_PASS)

    for host in RMQ_HOSTS:
        try:
            params = pika.ConnectionParameters(
                host=host,
                port=RMQ_PORT,
                credentials=credentials,
                heartbeat=300,
                blocked_connection_timeout=150,
                connection_attempts=3,
                retry_delay=2
            )
            return pika.BlockingConnection(params)
        except Exception:
            continue

    raise Exception("Could not connect to any RabbitMQ node")


def send_message(channel, request_queue, payload, callback_queue):
    correlation_id = str(uuid.uuid4())

    channel.queue_declare(
        queue=request_queue,
        durable=True,
        arguments={"x-queue-type": "quorum"}
    )
    channel.queue_declare(
        queue=callback_queue,
        durable=True,
        arguments={"x-queue-type": "quorum"}
    )

    print("\n[History FE Producer] Sending message")
    print("[History FE Producer] Queue:", request_queue)
    print("[History FE Producer] Payload:", payload)
    print("[History FE Producer] Correlation ID:", correlation_id)
    print("[History FE Producer] Reply-To:", callback_queue)

    channel.basic_publish(
        exchange="",
        routing_key=request_queue,
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            reply_to=callback_queue,
            correlation_id=correlation_id,
            delivery_mode=2
        )
    )

    return correlation_id


def send_add_history(
    username,
    song_id,
    track_name,
    artist_name,
    album_name="",
    artwork_url="",
    preview_url="",
    track_view_url=""
):
    connection = get_connection()
    channel = connection.channel()

    payload = {
        "action": "add_history",
        "username": username,
        "song_id": song_id,
        "track_name": track_name,
        "artist_name": artist_name,
        "album_name": album_name,
        "artwork_url": artwork_url,
        "preview_url": preview_url,
        "track_view_url": track_view_url
    }

    correlation_id = send_message(
        channel,
        HISTORY_ADD_REQUEST_QUEUE,
        payload,
        HISTORY_ADD_RESPONSE_QUEUE
    )

    connection.close()
    return correlation_id


def send_get_history(username):
    connection = get_connection()
    channel = connection.channel()

    payload = {
        "action": "get_history",
        "username": username
    }

    correlation_id = send_message(
        channel,
        HISTORY_GET_REQUEST_QUEUE,
        payload,
        HISTORY_GET_RESPONSE_QUEUE
    )

    connection.close()
    return correlation_id


def send_clear_history(username):
    connection = get_connection()
    channel = connection.channel()

    payload = {
        "action": "clear_history",
        "username": username
    }

    correlation_id = send_message(
        channel,
        HISTORY_CLEAR_REQUEST_QUEUE,
        payload,
        HISTORY_CLEAR_RESPONSE_QUEUE
    )

    connection.close()
    return correlation_id