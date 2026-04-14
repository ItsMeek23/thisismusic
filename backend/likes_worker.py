import json
import pika
import mysql.connector

RMQ_HOST = "100.114.37.13"
RMQ_PORT = 5672
RMQ_USER = "music"
RMQ_PASS = "music123"

DB_HOST = "100.78.226.13"
DB_PORT = 3306
DB_USER = "music"
DB_PASS = "changeme"
DB_NAME = "this_is_music"

def get_db():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME
    )

def get_user_id(cursor, username):
    cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
    row = cursor.fetchone()
    return row[0] if row else None

def handle_like(data):
    db = get_db()
    cursor = db.cursor()

    user_id = get_user_id(cursor, data["username"])
    if not user_id:
        return {"status": "fail", "message": "User not found"}

    try:
        cursor.execute("""
            INSERT INTO likes (user_id, song_id, track_name, artist_name, album_name, artwork_url, preview_url)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (
            user_id,
            data["song_id"],
            data.get("track_name"),
            data.get("artist_name"),
            data.get("album_name"),
            data.get("artwork_url"),
            data.get("preview_url")
        ))
        db.commit()
        return {"status": "success"}
    except Exception as e:
        return {"status": "fail", "message": str(e)}

def handle_get(data):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    user_id = get_user_id(cursor, data["username"])
    if not user_id:
        return {"status": "fail"}

    cursor.execute("""
        SELECT song_id, track_name, artist_name, album_name, artwork_url, preview_url
        FROM likes
        WHERE user_id=%s
    """, (user_id,))

    songs = cursor.fetchall()
    return {"status": "success", "songs": songs}

def handle_unlike(data):
    db = get_db()
    cursor = db.cursor()

    user_id = get_user_id(cursor, data["username"])
    if not user_id:
        return {"status": "fail"}

    cursor.execute("""
        DELETE FROM likes WHERE user_id=%s AND song_id=%s
    """, (user_id, data["song_id"]))
    db.commit()

    return {"status": "success"}

def main():
    creds = pika.PlainCredentials(RMQ_USER, RMQ_PASS)
    conn = pika.BlockingConnection(pika.ConnectionParameters(host=RMQ_HOST, credentials=creds))
    ch = conn.channel()

    ch.queue_declare(queue="likes.request")

    def callback(ch, method, props, body):
        data = json.loads(body)

        action = data.get("action")

        if action == "like":
            res = handle_like(data)
        elif action == "get":
            res = handle_get(data)
        elif action == "unlike":
            res = handle_unlike(data)
        else:
            res = {"status": "fail"}

        ch.basic_publish(
            exchange="",
            routing_key=props.reply_to,
            properties=pika.BasicProperties(correlation_id=props.correlation_id),
            body=json.dumps(res)
        )

        ch.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_consume(queue="likes.request", on_message_callback=callback)

    print("Likes worker running...")
    ch.start_consuming()

if __name__ == "__main__":
    main()