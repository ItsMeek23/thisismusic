import json
import uuid
import pika

RMQ_HOST = "100.114.37.13"
RMQ_PORT = 5672
RMQ_USER = "music"
RMQ_PASS = "music123"

DM_GET_USERS_FE_TO_BEFE = "dm.get_users.fe_to_befe"
DM_GET_CONVERSATION_FE_TO_BEFE = "dm.get_conversation.fe_to_befe"
DM_SEND_FE_TO_BEFE = "dm.send.fe_to_befe"


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


def send_get_dm_users(current_username):
    correlation_id = str(uuid.uuid4())

    payload = {
        "current_username": current_username,
        "correlation_id": correlation_id
    }

    connection = get_connection()
    channel = connection.channel()

    declare_queue(channel, DM_GET_USERS_FE_TO_BEFE)

    channel.basic_publish(
        exchange="",
        routing_key=DM_GET_USERS_FE_TO_BEFE,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )

    connection.close()
    return correlation_id


def send_get_conversation(current_username, other_username):
    correlation_id = str(uuid.uuid4())

    payload = {
        "current_username": current_username,
        "other_username": other_username,
        "correlation_id": correlation_id
    }

    connection = get_connection()
    channel = connection.channel()

    declare_queue(channel, DM_GET_CONVERSATION_FE_TO_BEFE)

    channel.basic_publish(
        exchange="",
        routing_key=DM_GET_CONVERSATION_FE_TO_BEFE,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )

    connection.close()
    return correlation_id


def send_dm_message(sender_username, receiver_username, body):
    correlation_id = str(uuid.uuid4())

    payload = {
        "sender_username": sender_username,
        "receiver_username": receiver_username,
        "body": body,
        "correlation_id": correlation_id
    }

    connection = get_connection()
    channel = connection.channel()

    declare_queue(channel, DM_SEND_FE_TO_BEFE)

    channel.basic_publish(
        exchange="",
        routing_key=DM_SEND_FE_TO_BEFE,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )

    connection.close()
    return correlation_id