import json
import time
import uuid
import pika

RMQ_HOST = "100.114.37.13"
RMQ_PORT = 5672
RMQ_USER = "music"
RMQ_PASS = "music123"

REVIEW_CREATE_FE_TO_BEFE = "review.create.fe_to_befe"
REVIEW_GET_FE_TO_BEFE = "review.get.fe_to_befe"

REVIEW_RESPONSE_BEDB_TO_FE = "review.response.bedb_to_fe"


def get_connection():
    credentials = pika.PlainCredentials(RMQ_USER, RMQ_PASS)
    params = pika.ConnectionParameters(
        host=RMQ_HOST,
        port=RMQ_PORT,
        credentials=credentials,
        heartbeat=30,
        blocked_connection_timeout=30
    )
    return pika.BlockingConnection(params)


def declare_quorum_queue(channel, queue_name):
    channel.queue_declare(
        queue=queue_name,
        durable=True,
        arguments={"x-queue-type": "quorum"}
    )


def wait_for_response(correlation_id, timeout=10):
    connection = get_connection()
    channel = connection.channel()

    declare_quorum_queue(channel, REVIEW_RESPONSE_BEDB_TO_FE)

    start_time = time.time()

    while time.time() - start_time < timeout:
        method_frame, properties, body = channel.basic_get(
            queue=REVIEW_RESPONSE_BEDB_TO_FE,
            auto_ack=False
        )

        if method_frame:
            try:
                response = json.loads(body.decode("utf-8"))
            except Exception:
                channel.basic_ack(method_frame.delivery_tag)
                continue

            if response.get("correlation_id") == correlation_id:
                channel.basic_ack(method_frame.delivery_tag)
                connection.close()
                return response

            channel.basic_nack(method_frame.delivery_tag, requeue=True)

        time.sleep(0.25)

    connection.close()

    return {
        "success": False,
        "message": "Timed out waiting for review response."
    }


def create_review(username, song_id, song_name, artist, rating, review_text):
    correlation_id = str(uuid.uuid4())

    payload = {
        "action": "create_review",
        "correlation_id": correlation_id,
        "username": username,
        "song_id": song_id,
        "song_name": song_name,
        "artist": artist,
        "rating": rating,
        "review": review_text
    }

    connection = get_connection()
    channel = connection.channel()

    declare_quorum_queue(channel, REVIEW_CREATE_FE_TO_BEFE)
    declare_quorum_queue(channel, REVIEW_RESPONSE_BEDB_TO_FE)

    channel.basic_publish(
        exchange="",
        routing_key=REVIEW_CREATE_FE_TO_BEFE,
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            delivery_mode=2,
            correlation_id=correlation_id
        )
    )

    connection.close()

    return wait_for_response(correlation_id)


def get_reviews(song_id):
    correlation_id = str(uuid.uuid4())

    payload = {
        "action": "get_reviews",
        "correlation_id": correlation_id,
        "song_id": song_id
    }

    connection = get_connection()
    channel = connection.channel()

    declare_quorum_queue(channel, REVIEW_GET_FE_TO_BEFE)
    declare_quorum_queue(channel, REVIEW_RESPONSE_BEDB_TO_FE)

    channel.basic_publish(
        exchange="",
        routing_key=REVIEW_GET_FE_TO_BEFE,
        body=json.dumps(payload),
        properties=pika.BasicProperties(
            delivery_mode=2,
            correlation_id=correlation_id
        )
    )

    connection.close()

    return wait_for_response(correlation_id)