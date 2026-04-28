import json
import uuid
import pika

RMQ_HOSTS = [
    "100.94.40.126",  # RMQ3 - Meek
    "100.65.228.57",  # RMQ2 - Amaan
    "100.114.37.13",  # RMQ1 - Daniel
]

RMQ_PORT = 5672
RMQ_USER = "music"
RMQ_PASS = "music123"

DISCUSSION_CREATE_POST_FE_TO_BEFE = "discussion.create_post.fe_to_befe"
DISCUSSION_GET_POSTS_FE_TO_BEFE = "discussion.get_posts.fe_to_befe"
DISCUSSION_CREATE_REPLY_FE_TO_BEFE = "discussion.create_reply.fe_to_befe"

DISCUSSION_EDIT_POST_FE_TO_BEFE = "discussion.edit_post.fe_to_befe"
DISCUSSION_DELETE_POST_FE_TO_BEFE = "discussion.delete_post.fe_to_befe"


def get_connection():
    credentials = pika.PlainCredentials(RMQ_USER, RMQ_PASS)
    last_error = None

    for host in RMQ_HOSTS:
        try:
            print(f"[discussion_producer] Trying RMQ node: {host}")
            params = pika.ConnectionParameters(
                host=host,
                port=RMQ_PORT,
                credentials=credentials,
                heartbeat=30,
                blocked_connection_timeout=30
            )
            return pika.BlockingConnection(params)
        except Exception as e:
            print(f"[discussion_producer] Failed RMQ node {host}: {e}")
            last_error = e

    raise last_error


def declare_queue(channel, queue_name):
    channel.queue_declare(
        queue=queue_name,
        durable=True,
        arguments={"x-queue-type": "quorum"}
    )


def publish_payload(queue_name, payload):
    connection = get_connection()
    channel = connection.channel()

    declare_queue(channel, queue_name)

    channel.basic_publish(
        exchange="",
        routing_key=queue_name,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )

    connection.close()


def send_create_discussion_post(user_id, username, title, body):
    correlation_id = str(uuid.uuid4())

    payload = {
        "user_id": user_id,
        "username": username,
        "title": title,
        "body": body,
        "correlation_id": correlation_id
    }

    publish_payload(DISCUSSION_CREATE_POST_FE_TO_BEFE, payload)
    return correlation_id


def send_get_discussion_posts():
    correlation_id = str(uuid.uuid4())

    payload = {
        "correlation_id": correlation_id
    }

    publish_payload(DISCUSSION_GET_POSTS_FE_TO_BEFE, payload)
    return correlation_id


def send_create_discussion_reply(post_id, user_id, username, body):
    correlation_id = str(uuid.uuid4())

    payload = {
        "post_id": post_id,
        "user_id": user_id,
        "username": username,
        "body": body,
        "correlation_id": correlation_id
    }

    publish_payload(DISCUSSION_CREATE_REPLY_FE_TO_BEFE, payload)
    return correlation_id


def send_edit_discussion_post(post_id, user_id, username, title, body):
    correlation_id = str(uuid.uuid4())

    payload = {
        "post_id": post_id,
        "user_id": user_id,
        "username": username,
        "title": title,
        "body": body,
        "correlation_id": correlation_id
    }

    publish_payload(DISCUSSION_EDIT_POST_FE_TO_BEFE, payload)
    return correlation_id


def send_delete_discussion_post(post_id, user_id, username):
    correlation_id = str(uuid.uuid4())

    payload = {
        "post_id": post_id,
        "user_id": user_id,
        "username": username,
        "correlation_id": correlation_id
    }

    publish_payload(DISCUSSION_DELETE_POST_FE_TO_BEFE, payload)
    return correlation_id