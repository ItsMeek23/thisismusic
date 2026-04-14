B. FE response listener
This is a separate FE-side consumer that listens for the final response.
import json
import pika

RMQ_HOST = "100.114.37.13"
RMQ_PORT = 5672
RMQ_USER = "music"
RMQ_PASS = "music123"

REGISTER_RESPONSE_QUEUE = "auth.register.response"
LOGIN_RESPONSE_QUEUE = "auth.login.response"


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


def on_response(ch, method, props, body):
   print("\n[FE Listener] Response received")
   print("[FE Listener] Queue:", method.routing_key)
   print("[FE Listener] Correlation ID:", props.correlation_id)
   print("[FE Listener] Body:", body.decode("utf-8"))

   ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
   connection = get_connection()
   channel = connection.channel()

   channel.queue_declare(
    queue=REGISTER_RESPONSE_QUEUE,
    durable=True,
    arguments={"x-queue-type": "quorum"}
)

channel.queue_declare(
    queue=LOGIN_RESPONSE_QUEUE,
    durable=True,
    arguments={"x-queue-type": "quorum"}
)

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
