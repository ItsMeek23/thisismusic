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

REGISTER_REQUEST_QUEUE = "auth.register.fe_to_befe"
LOGIN_REQUEST_QUEUE = "auth.login.fe_to_befe"
SEARCH_REQUEST_QUEUE = "search.request.fe_to_befe"
LIKE_SONG_REQUEST_QUEUE = "likes.add.fe_to_befe"
GET_LIKED_SONGS_REQUEST_QUEUE = "likes.get.fe_to_befe"
UNLIKE_SONG_REQUEST_QUEUE = "likes.remove.fe_to_befe"
FORGOT_PASSWORD_REQUEST_QUEUE = "auth.forgot_password.fe_to_befe"

REGISTER_RESPONSE_QUEUE = "auth.register.bedb_to_fe"
LOGIN_RESPONSE_QUEUE = "auth.login.bedb_to_fe"
SEARCH_RESPONSE_QUEUE = "search.response.bedb_to_fe"
LIKES_ADD_RESPONSE_QUEUE = "likes.add.bedb_to_fe"
LIKES_GET_RESPONSE_QUEUE = "likes.get.bedb_to_fe"
LIKES_REMOVE_RESPONSE_QUEUE = "likes.remove.bedb_to_fe"
FORGOT_PASSWORD_RESPONSE_QUEUE = "auth.forgot_password.bedb_to_fe"


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
                connection_attempts=1,
                retry_delay=0
            )
            return pika.BlockingConnection(params)
        except Exception:
            continue
    raise Exception("Could not connect to any RabbitMQ node")


def send_message(channel, request_queue, payload, callback_queue):
    correlation_id = str(uuid.uuid4())

    channel.queue_declare(queue=request_queue, durable=True, arguments={"x-queue-type": "quorum"})
    channel.queue_declare(queue=callback_queue, durable=True, arguments={"x-queue-type": "quorum"})

    print("\n[FE Producer] Sending message")
    print("[FE Producer] Queue:", request_queue)
    print("[FE Producer] Payload:", payload)
    print("[FE Producer] Correlation ID:", correlation_id)
    print("[FE Producer] Reply-To:", callback_queue)

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


def send_register(username, email, password):
    connection = get_connection()
    channel = connection.channel()
    payload = {"action": "register", "username": username, "email": email, "password": password}
    correlation_id = send_message(channel, REGISTER_REQUEST_QUEUE, payload, REGISTER_RESPONSE_QUEUE)
    connection.close()
    return correlation_id


def send_login(username, password, ip_address="unknown", user_agent="unknown"):
    connection = get_connection()
    channel = connection.channel()
    payload = {"action": "login", "username": username, "password": password, "ip_address": ip_address, "user_agent": user_agent}
    correlation_id = send_message(channel, LOGIN_REQUEST_QUEUE, payload, LOGIN_RESPONSE_QUEUE)
    connection.close()
    return correlation_id


def send_forgot_password(username, new_password):
    connection = get_connection()
    channel = connection.channel()
    payload = {"action": "forgot_password", "username": username, "new_password": new_password}
    correlation_id = send_message(channel, FORGOT_PASSWORD_REQUEST_QUEUE, payload, FORGOT_PASSWORD_RESPONSE_QUEUE)
    connection.close()
    return correlation_id


def send_search(query, username=""):
    connection = get_connection()
    channel = connection.channel()
    payload = {"action": "search", "query": query, "username": username}
    correlation_id = send_message(channel, SEARCH_REQUEST_QUEUE, payload, SEARCH_RESPONSE_QUEUE)
    connection.close()
    return correlation_id


def send_like_song(username, song_id, track_name, artist_name, album_name="", artwork_url="", preview_url="", track_view_url=""):
    connection = get_connection()
    channel = connection.channel()
    payload = {
        "action": "like_song",
        "username": username,
        "song_id": song_id,
        "track_name": track_name,
        "artist_name": artist_name,
        "album_name": album_name,
        "artwork_url": artwork_url,
        "preview_url": preview_url,
        "track_view_url": track_view_url
    }
    correlation_id = send_message(channel, LIKE_SONG_REQUEST_QUEUE, payload, LIKES_ADD_RESPONSE_QUEUE)
    connection.close()
    return correlation_id


def send_get_liked_songs(username):
    connection = get_connection()
    channel = connection.channel()
    payload = {"action": "get_liked_songs", "username": username}
    correlation_id = send_message(channel, GET_LIKED_SONGS_REQUEST_QUEUE, payload, LIKES_GET_RESPONSE_QUEUE)
    connection.close()
    return correlation_id


def send_unlike_song(username, song_id):
    connection = get_connection()
    channel = connection.channel()
    payload = {"action": "unlike_song", "username": username, "song_id": song_id}
    correlation_id = send_message(channel, UNLIKE_SONG_REQUEST_QUEUE, payload, LIKES_REMOVE_RESPONSE_QUEUE)
    connection.close()
    return correlation_id