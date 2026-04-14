from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, unquote, parse_qs
import os
import mimetypes
import json
import re

from fe_producer import (
    send_register,
    send_login,
    send_search,
    send_like_song,
    send_get_liked_songs,
    send_unlike_song,
    send_forgot_password
)
from history_producer import (
    send_add_history,
    send_get_history,
    send_clear_history
)
from fe_response_consumer import wait_for_response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

REGISTER_RESPONSE_QUEUE = "auth.register.bedb_to_fe"
LOGIN_RESPONSE_QUEUE = "auth.login.bedb_to_fe"
FORGOT_PASSWORD_RESPONSE_QUEUE = "auth.forgot_password.bedb_to_fe"
SEARCH_RESPONSE_QUEUE = "search.response.bedb_to_fe"

LIKES_ADD_RESPONSE_QUEUE = "likes.add.bedb_to_fe"
LIKES_GET_RESPONSE_QUEUE = "likes.get.bedb_to_fe"
LIKES_REMOVE_RESPONSE_QUEUE = "likes.remove.bedb_to_fe"

HISTORY_ADD_RESPONSE_QUEUE = "history.add.bedb_to_fe"
HISTORY_GET_RESPONSE_QUEUE = "history.get.bedb_to_fe"
HISTORY_CLEAR_RESPONSE_QUEUE = "history.clear.bedb_to_fe"


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def is_valid_password(password):
    pattern = r"^(?=.*[0-9])(?=.*[^A-Za-z0-9]).{8,}$"
    return re.match(pattern, password) is not None


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        return

    def get_cookie_value(self, key):
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return None

        parts = cookie_header.split(";")
        for part in parts:
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == key:
                    return v
        return None

    def get_logged_in_username(self):
        return self.get_cookie_value("username")

    def is_json_request(self):
        content_type = self.headers.get("Content-Type", "")
        accept = self.headers.get("Accept", "")
        x_requested_with = self.headers.get("X-Requested-With", "")

        return (
            "application/json" in content_type
            or "application/json" in accept
            or x_requested_with.lower() == "xmlhttprequest"
        )

    def send_redirect(self, location, cookies=None):
        self.send_response(302)
        self.send_header("Location", location)

        if cookies:
            for cookie in cookies:
                self.send_header("Set-Cookie", cookie)

        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def serve_file(self, file_path, content_type=None, send_body=True):
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return False

        if content_type is None:
            guessed, _ = mimetypes.guess_type(file_path)
            content_type = guessed or "application/octet-stream"

        data = read_file(file_path)

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()

        if send_body:
            self.wfile.write(data)

        self.close_connection = True
        return True

    def serve_template(self, filename, send_body=True):
        file_path = os.path.join(TEMPLATES_DIR, filename)
        return self.serve_file(
            file_path,
            content_type="text/html; charset=utf-8",
            send_body=send_body
        )

    def serve_static(self, url_path, send_body=True):
        rel = url_path[len("/static/"):]
        rel = unquote(rel).lstrip("/")

        static_root = os.path.abspath(STATIC_DIR)
        full_path = os.path.abspath(os.path.normpath(os.path.join(static_root, rel)))

        if not full_path.startswith(static_root):
            return False

        return self.serve_file(full_path, content_type=None, send_body=send_body)

    def send_html(self, html, status=200):
        data = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def send_json(self, payload, status=200, cookies=None):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))

        if cookies:
            for cookie in cookies:
                self.send_header("Set-Cookie", cookie)

        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def parse_request_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b""
        content_type = self.headers.get("Content-Type", "")

        if "application/json" in content_type:
            try:
                return json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                return {}

        if "application/x-www-form-urlencoded" in content_type:
            parsed = parse_qs(raw.decode("utf-8"))
            return {k: v[0] if isinstance(v, list) and v else "" for k, v in parsed.items()}

        return {}

    def handle_register(self):
        body = self.parse_request_body()
        email = str(body.get("email", "")).strip()
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", "")).strip()

        if not email or not username or not password:
            self.send_json(
                {"status": "fail", "message": "Email, username, and password are required"},
                status=400
            )
            return

        if not is_valid_password(password):
            self.send_json(
                {
                    "status": "fail",
                    "message": "Password must be at least 8 characters long and include at least 1 number and 1 special character."
                },
                status=400
            )
            return

        try:
            correlation_id = send_register(username, email, password)
            response = wait_for_response(REGISTER_RESPONSE_QUEUE, correlation_id)
            self.send_json(response, status=200)

        except Exception as e:
            print("REGISTER ERROR:", e)
            self.send_json(
                {
                    "status": "fail",
                    "message": "Registration service unavailable. Please make sure RabbitMQ and backend services are running."
                },
                status=503
            )

    def handle_login(self):
        body = self.parse_request_body()
        username = str(body.get("username", "")).strip()
        password = str(body.get("password", "")).strip()

        if not username or not password:
            self.send_json(
                {"status": "fail", "message": "Username and password are required"},
                status=400
            )
            return

        try:
            correlation_id = send_login(username, password)
            response = wait_for_response(LOGIN_RESPONSE_QUEUE, correlation_id)

            if isinstance(response, dict) and response.get("status") == "success":
                response_username = str(response.get("username", username)).strip() or username
                cookie = f"username={response_username}; Path=/; HttpOnly; SameSite=Lax"

                if self.is_json_request():
                    self.send_json(response, status=200, cookies=[cookie])
                else:
                    self.send_redirect("/home", cookies=[cookie])
                return

            self.send_json(response, status=200)

        except Exception as e:
            print("LOGIN ERROR:", e)
            self.send_json(
                {
                    "status": "fail",
                    "message": "Login service unavailable. Please make sure RabbitMQ and backend services are running."
                },
                status=503
            )

    def handle_forgot_password(self):
        body = self.parse_request_body()
        username = str(body.get("username", "")).strip()
        new_password = str(body.get("new_password", "")).strip()
        confirm_password = str(body.get("confirm_password", "")).strip()

        if not username or not new_password or not confirm_password:
            self.send_json(
                {
                    "status": "fail",
                    "message": "Username, new password, and confirm password are required"
                },
                status=400
            )
            return

        if new_password != confirm_password:
            self.send_json(
                {
                    "status": "fail",
                    "message": "Passwords do not match"
                },
                status=400
            )
            return

        if not is_valid_password(new_password):
            self.send_json(
                {
                    "status": "fail",
                    "message": "Password must be at least 8 characters long and include at least 1 number and 1 special character."
                },
                status=400
            )
            return

        try:
            correlation_id = send_forgot_password(username, new_password)
            response = wait_for_response(FORGOT_PASSWORD_RESPONSE_QUEUE, correlation_id)
            self.send_json(response, status=200)

        except Exception as e:
            print("FORGOT PASSWORD ERROR:", e)
            self.send_json(
                {
                    "status": "fail",
                    "message": "Password reset service unavailable. Please make sure RabbitMQ and backend services are running."
                },
                status=503
            )

    def handle_itunes_search(self, send_body=True):
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)
        term = query_params.get("q", [""])[0].strip()

        if not term:
            if send_body:
                self.send_json(
                    {
                        "songs": [],
                        "albums": [],
                        "message": "Missing search query"
                    },
                    status=400
                )
            else:
                self.send_response(400)
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
            return True

        try:
            correlation_id = send_search(term)
            response = wait_for_response(SEARCH_RESPONSE_QUEUE, correlation_id)

            if send_body:
                self.send_json(response, status=200)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

        except Exception:
            if send_body:
                self.send_json(
                    {
                        "songs": [],
                        "albums": [],
                        "message": "Search service unavailable. Please make sure RabbitMQ and backend services are running."
                    },
                    status=503
                )
            else:
                self.send_response(503)
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

        return True

    def handle_like_song(self):
        body = self.parse_request_body()

        username = str(body.get("username", "")).strip()
        song_id = str(body.get("song_id", "")).strip()
        track_name = str(body.get("track_name", "")).strip()
        artist_name = str(body.get("artist_name", "")).strip()
        album_name = str(body.get("album_name", "")).strip()
        artwork_url = str(body.get("artwork_url", "")).strip()
        preview_url = str(body.get("preview_url", "")).strip()
        track_view_url = str(body.get("track_view_url", "")).strip()

        if not username or not song_id or not track_name or not artist_name:
            self.send_json(
                {
                    "status": "fail",
                    "message": "username, song_id, track_name, and artist_name are required"
                },
                status=400
            )
            return

        try:
            correlation_id = send_like_song(
                username=username,
                song_id=song_id,
                track_name=track_name,
                artist_name=artist_name,
                album_name=album_name,
                artwork_url=artwork_url,
                preview_url=preview_url,
                track_view_url=track_view_url
            )
            response = wait_for_response(LIKES_ADD_RESPONSE_QUEUE, correlation_id)
            self.send_json(response, status=200)

        except Exception as e:
            print("LIKE SONG ERROR:", e)
            self.send_json(
                {
                    "status": "fail",
                    "message": "Like song service unavailable. Please make sure RabbitMQ and backend services are running."
                },
                status=503
            )

    def handle_get_liked_songs(self):
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)

        username = query_params.get("username", [""])[0].strip()
        if not username:
            username = self.get_logged_in_username() or ""

        if not username:
            self.send_json(
                {
                    "status": "fail",
                    "message": "username is required"
                },
                status=400
            )
            return True

        try:
            correlation_id = send_get_liked_songs(username)
            response = wait_for_response(LIKES_GET_RESPONSE_QUEUE, correlation_id)
            self.send_json(response, status=200)

        except Exception as e:
            print("GET LIKED SONGS ERROR:", e)
            self.send_json(
                {
                    "status": "fail",
                    "songs": [],
                    "message": "Liked songs service unavailable. Please make sure RabbitMQ and backend services are running."
                },
                status=503
            )

        return True

    def handle_unlike_song(self):
        body = self.parse_request_body()

        username = str(body.get("username", "")).strip()
        song_id = str(body.get("song_id", "")).strip()

        if not username:
            username = self.get_logged_in_username() or ""

        if not username or not song_id:
            self.send_json(
                {
                    "status": "fail",
                    "message": "username and song_id are required"
                },
                status=400
            )
            return

        try:
            correlation_id = send_unlike_song(username, song_id)
            response = wait_for_response(LIKES_REMOVE_RESPONSE_QUEUE, correlation_id)
            self.send_json(response, status=200)

        except Exception as e:
            print("UNLIKE SONG ERROR:", e)
            self.send_json(
                {
                    "status": "fail",
                    "message": "Unlike song service unavailable. Please make sure RabbitMQ and backend services are running."
                },
                status=503
            )

    def handle_add_history(self):
        body = self.parse_request_body()

        username = str(body.get("username", "")).strip()
        song_id = str(body.get("song_id", "")).strip()
        track_name = str(body.get("track_name", "")).strip()
        artist_name = str(body.get("artist_name", "")).strip()
        album_name = str(body.get("album_name", "")).strip()
        artwork_url = str(body.get("artwork_url", "")).strip()
        preview_url = str(body.get("preview_url", "")).strip()
        track_view_url = str(body.get("track_view_url", "")).strip()

        if not username:
            username = self.get_logged_in_username() or ""

        if not username or not song_id or not track_name or not artist_name:
            self.send_json(
                {
                    "status": "fail",
                    "message": "username, song_id, track_name, and artist_name are required"
                },
                status=400
            )
            return

        try:
            correlation_id = send_add_history(
                username=username,
                song_id=song_id,
                track_name=track_name,
                artist_name=artist_name,
                album_name=album_name,
                artwork_url=artwork_url,
                preview_url=preview_url,
                track_view_url=track_view_url
            )
            response = wait_for_response(HISTORY_ADD_RESPONSE_QUEUE, correlation_id)
            self.send_json(response, status=200)

        except Exception as e:
            print("ADD HISTORY ERROR:", e)
            self.send_json(
                {
                    "status": "fail",
                    "message": "History add service unavailable. Please make sure RabbitMQ and backend services are running."
                },
                status=503
            )

    def handle_get_history(self):
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)

        username = query_params.get("username", [""])[0].strip()
        if not username:
            username = self.get_logged_in_username() or ""

        if not username:
            self.send_json(
                {
                    "status": "fail",
                    "songs": [],
                    "message": "username is required"
                },
                status=400
            )
            return True

        try:
            correlation_id = send_get_history(username)
            response = wait_for_response(HISTORY_GET_RESPONSE_QUEUE, correlation_id)
            self.send_json(response, status=200)

        except Exception as e:
            print("GET HISTORY ERROR:", e)
            self.send_json(
                {
                    "status": "fail",
                    "songs": [],
                    "message": "History service unavailable. Please make sure RabbitMQ and backend services are running."
                },
                status=503
            )

        return True

    def handle_clear_history(self):
        body = self.parse_request_body()

        username = str(body.get("username", "")).strip()
        if not username:
            username = self.get_logged_in_username() or ""

        if not username:
            self.send_json(
                {
                    "status": "fail",
                    "message": "username is required"
                },
                status=400
            )
            return

        try:
            correlation_id = send_clear_history(username)
            response = wait_for_response(HISTORY_CLEAR_RESPONSE_QUEUE, correlation_id)
            self.send_json(response, status=200)

        except Exception as e:
            print("CLEAR HISTORY ERROR:", e)
            self.send_json(
                {
                    "status": "fail",
                    "message": "History clear service unavailable. Please make sure RabbitMQ and backend services are running."
                },
                status=503
            )

    def do_GET(self):
        self.route(send_body=True)

    def do_HEAD(self):
        self.route(send_body=False)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/register":
            self.handle_register()
            return

        if path == "/api/login":
            self.handle_login()
            return

        if path == "/api/forgot-password":
            self.handle_forgot_password()
            return

        if path == "/api/like-song":
            self.handle_like_song()
            return

        if path == "/api/unlike-song":
            self.handle_unlike_song()
            return

        if path == "/api/history/add":
            self.handle_add_history()
            return

        if path == "/api/history/clear":
            self.handle_clear_history()
            return

        self.send_json({"status": "fail", "message": "Not Found"}, status=404)

    def route(self, send_body=True):
        parsed = urlparse(self.path)
        path = parsed.path

                # HEALTH CHECK (for NGINX)
        if path == "/health":
            msg = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.send_header("Connection", "close")
            self.end_headers()

            if send_body:
                self.wfile.write(msg)

            self.close_connection = True
            return True

        protected_paths = {
            "/home", "/home.html",
            "/liked", "/liked.html",
            "/playlists", "/playlists.html",
            "/playlist", "/playlist.html",
            "/trending", "/trending.html",
            "/history", "/history.html",
            "/profile", "/profile.html"
        }

        if path in protected_paths and not self.get_logged_in_username():
            self.send_redirect("/login")
            return True

        if path.startswith("/static/"):
            if self.serve_static(path, send_body=send_body):
                return True

        if path == "/api/search":
            return self.handle_itunes_search(send_body=send_body)

        if path == "/api/liked-songs":
            return self.handle_get_liked_songs()

        if path == "/api/history/get":
            return self.handle_get_history()

        if path == "/" or path == "/index.html":
            return self.serve_template("index.html", send_body=send_body)

        if path == "/login" or path == "/login.html":
            return self.serve_template("login.html", send_body=send_body)

        if path == "/register" or path == "/register.html":
            return self.serve_template("register.html", send_body=send_body)

        if path == "/forgot-password" or path == "/forgot-password.html":
            return self.serve_template("forgot_password.html", send_body=send_body)

        if path == "/home" or path == "/home.html":
            return self.serve_template("home.html", send_body=send_body)

        if path == "/liked" or path == "/liked.html":
            return self.serve_template("liked.html", send_body=send_body)

        if path == "/playlists" or path == "/playlists.html":
            return self.serve_template("playlists.html", send_body=send_body)

        if path == "/playlist" or path == "/playlist.html":
            return self.serve_template("playlist.html", send_body=send_body)

        if path == "/trending" or path == "/trending.html":
            return self.serve_template("trending.html", send_body=send_body)

        if path == "/history" or path == "/history.html":
            return self.serve_template("history.html", send_body=send_body)

        if path == "/profile" or path == "/profile.html":
            return self.serve_template("profile.html", send_body=send_body)

        if path == "/logout":
            clear_cookie = "username=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
            self.send_redirect("/", cookies=[clear_cookie])
            return True

        msg = b"Not Found"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(msg)))
        self.send_header("Connection", "close")
        self.end_headers()

        if send_body:
            self.wfile.write(msg)

        self.close_connection = True
        return True


if __name__ == "__main__":
    HOST = "0.0.0.0"
    PORT = 7012

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Frontend running on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()