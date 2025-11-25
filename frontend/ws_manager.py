# ws_manager.py
import websocket
import json
import uuid
import threading
import queue
import time

WS_URL = "ws://localhost:8000/ws"

class WebSocketManager:
    def __init__(self, message_queue):
        self.uid = str(uuid.uuid4())
        self._message_queue = message_queue
        self._outbound_q = queue.Queue()
        self._ws_connected = False
        self._last_error = None
        self._should_stop = False
        self._listener_thread = None

    def start(self):
        """Starts background WebSocket listener."""
        if self._listener_thread is None:
            self._listener_thread = threading.Thread(target=self._listener_loop, daemon=True)
            self._listener_thread.start()

    def stop(self):
        """Stops WS listener."""
        self._should_stop = True

    # ---- Public API ----
    def send(self, payload: dict):
        """Queue outbound message (safely)."""
        payload = dict(payload)
        payload["uid"] = self.uid
        self._outbound_q.put(payload)

    def is_connected(self):
        return self._ws_connected

    def last_error(self):
        return self._last_error

    # ---- Internal ----
    def _listener_loop(self):
        websocket.enableTrace(False)
        backoff = 1
        max_backoff = 30

        def on_open(ws):
            self._ws_connected = True
            self._last_error = None
            print("[ws] connected")

        def on_message(ws, message):
            # Put raw JSON-parsed object(s) into the queue for main thread to consume
            try:
                data = json.loads(message)
            except Exception:
                data = message
            # Non-blocking put (if queue is full, we drop oldest to avoid blocking)
            try:
                self._message_queue.put_nowait(data)
            except queue.Full:
                try:
                    _ = self._message_queue.get_nowait()  # drop one
                except queue.Empty:
                    pass
                try:
                    self._message_queue.put_nowait(data)
                except queue.Full:
                    print("[ws] message queue full, dropped message")

        def on_error(ws, error):
            self._last_error = str(error)
            print("[ws] error:", error)

        def on_close(ws, code, msg):
            self._ws_connected = False
            print(f"[ws] closed: {code} {msg}")

        while not self._should_stop:
            try:
                ws_app = websocket.WebSocketApp(
                    f"{WS_URL}?uid={self.uid}",
                    on_open=on_open,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                )

                ws_thread = threading.Thread(
                    target=ws_app.run_forever,
                    kwargs={"ping_interval": 20, "ping_timeout": 10},
                    daemon=True,
                )
                ws_thread.start()

                # Wait until connection established or timeout
                start = time.time()
                while not self._ws_connected and time.time() - start < 5:
                    time.sleep(0.1)

                # Send loop
                while self._ws_connected and not self._should_stop:
                    try:
                        msg = self._outbound_q.get(timeout=1)
                        ws_app.send(json.dumps(msg))
                    except queue.Empty:
                        continue
                    except Exception as e:
                        print("[ws] send failed:", e)
                        self._outbound_q.put(msg)  # requeue
                        break

                # Reconnect with backoff
                self._ws_connected = False

                if self._should_stop:
                    break

                print(f"[ws] reconnecting in {backoff}s...")
                time.sleep(backoff)
                backoff = min(max_backoff, backoff * 2)

            except Exception as e:
                print("[ws] loop exception:", e)
                self._ws_connected = False
                time.sleep(backoff)
                backoff = min(max_backoff, backoff * 2)
