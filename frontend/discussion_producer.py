import json
import uuid
import pika

RMQ_HOST = "100.114.37.13"
RMQ_PORT = 5672
RMQ_USER = "music"
RMQ_PASS = "music123"

DISCUSSION_CREATE_POST_FE_TO_BEFE = "discussion.create_post.fe_to_befe"
DISCUSSION_GET_POSTS_FE_TO_BEFE = "discussion.get_posts.fe_to_befe"
DISCUSSION_CREATE_REPLY_FE_TO_BEFE = "discussion.create_reply.fe_to_befe"


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


def declare_queue(channel, queue_name):
    channel.queue_declare(
        queue=queue_name,
        durable=True,
        arguments={"x-queue-type": "quorum"}
    )


def send_create_discussion_post(user_id, username, title, body):
    correlation_id = str(uuid.uuid4())

    payload = {
        "user_id": user_id,
        "username": username,
        "title": title,
        "body": body,
        "correlation_id": correlation_id
    }

    connection = get_connection()
    channel = connection.channel()

    declare_queue(channel, DISCUSSION_CREATE_POST_FE_TO_BEFE)

    channel.basic_publish(
        exchange="",
        routing_key=DISCUSSION_CREATE_POST_FE_TO_BEFE,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )

    connection.close()
    return correlation_id


def send_get_discussion_posts():
    correlation_id = str(uuid.uuid4())

    payload = {
        "correlation_id": correlation_id
    }

    connection = get_connection()
    channel = connection.channel()

    declare_queue(channel, DISCUSSION_GET_POSTS_FE_TO_BEFE)

    channel.basic_publish(
        exchange="",
        routing_key=DISCUSSION_GET_POSTS_FE_TO_BEFE,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )

    connection.close()
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

    connection = get_connection()
    channel = connection.channel()

    declare_queue(channel, DISCUSSION_CREATE_REPLY_FE_TO_BEFE)

    channel.basic_publish(
        exchange="",
        routing_key=DISCUSSION_CREATE_REPLY_FE_TO_BEFE,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )

    connection.close()
    return correlation_id