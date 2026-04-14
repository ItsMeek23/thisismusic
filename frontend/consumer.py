import json
import time
import pika

RMQ_HOST = "100.114.37.13"
RMQ_PORT = 5672
RMQ_USER = "music"
RMQ_PASS = "music123"


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


def create_callback_queue(channel):
    result = channel.queue_declare(queue="", exclusive=True)
    queue_name = result.method.queue
    print(f"[FE Consumer] Waiting on callback queue: {queue_name}")
    return queue_name


def wait_for_response(channel, callback_queue, correlation_id, timeout=10):
    start_time = time.time()

    while time.time() - start_time < timeout:
        method_frame, header_frame, body = channel.basic_get(
            queue=callback_queue,
            auto_ack=True
        )

        if method_frame:
            if header_frame.correlation_id == correlation_id:
                print(f"[FE Consumer] Received response for correlation ID: {correlation_id}")
                print(f"[FE Consumer] Raw body: {body.decode('utf-8')}")
                try:
                    return json.loads(body.decode("utf-8"))
                except Exception:
                    return {
                        "status": "fail",
                        "message": "Invalid JSON response from backend"
                    }

        time.sleep(0.1)

    print("[FE Consumer] Timeout waiting for response")
    return {
        "status": "fail",
        "message": "Backend timeout or no response received"
    }
