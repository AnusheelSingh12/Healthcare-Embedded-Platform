import json
import threading
from collections.abc import Callable

import serial


class SerialListener:
    def __init__(
        self,
        on_event: Callable[[dict], None],
        on_error: Callable[[str], None],
        baudrate: int = 9600,
        timeout: float = 1.0,
    ) -> None:
        self._on_event = on_event
        self._on_error = on_error
        self._baudrate = baudrate
        self._timeout = timeout
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._serial_conn: serial.Serial | None = None
        self._active_port: str | None = None
        self._lock = threading.Lock()

    @property
    def active_port(self) -> str | None:
        return self._active_port

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, port: str) -> None:
        with self._lock:
            if self.is_running:
                raise RuntimeError("Listener is already running")

            self._stop_event.clear()
            self._active_port = port
            self._thread = threading.Thread(target=self._listen_loop, args=(port,), daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            if self._serial_conn and self._serial_conn.is_open:
                self._serial_conn.close()

        if self._thread:
            self._thread.join(timeout=2.0)

        with self._lock:
            self._thread = None
            self._serial_conn = None
            self._active_port = None

    def _listen_loop(self, port: str) -> None:
        try:
            self._serial_conn = serial.Serial(port, self._baudrate, timeout=self._timeout)
            while not self._stop_event.is_set():
                raw_bytes = self._serial_conn.readline()
                if not raw_bytes:
                    continue
                raw_line = raw_bytes.decode("utf-8", errors="ignore").strip()
                event_payload = self._parse_event(raw_line)
                if event_payload:
                    self._on_event(event_payload)
        except Exception as exc:
            self._on_error(f"Serial listener error on {port}: {exc}")
        finally:
            if self._serial_conn and self._serial_conn.is_open:
                self._serial_conn.close()

    def _parse_event(self, raw_line: str) -> dict | None:
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            self._on_error(f"Discarded non-JSON payload: {raw_line}")
            return None

        if not isinstance(payload, dict):
            self._on_error(f"Discarded JSON payload (not object): {raw_line}")
            return None

        uid = payload.get("UID")
        if not isinstance(uid, str) or not uid.strip():
            self._on_error(f"Discarded JSON payload (missing UID): {raw_line}")
            return None

        item_name = payload.get("item_name")
        action = payload.get("action")

        if not isinstance(item_name, str) or not item_name.strip():
            self._on_error(f"Discarded JSON payload (missing item_name): {raw_line}")
            return None
        if not isinstance(action, str) or not action.strip():
            self._on_error(f"Discarded JSON payload (missing action): {raw_line}")
            return None
        gauze_count = payload.get("gauze_count", 0)
        tools_missing = payload.get("tools_missing", 0)

        try:
            gauze_count = int(gauze_count)
            tools_missing = int(tools_missing)
        except (TypeError, ValueError):
            self._on_error(f"Discarded JSON payload (invalid counters): {raw_line}")
            return None

        return {
            "UID": uid.strip(),
            "item_name": item_name.strip(),
            "action": action.strip().upper(),
            "gauze_count": max(gauze_count, 0),
            "tools_missing": max(tools_missing, 0),
        }
