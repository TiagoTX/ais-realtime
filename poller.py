from threading import Event, Lock, Thread
from time import monotonic
from datetime import timedelta

from adapter import build_time_window, run_once


class PollingWorker:
    def __init__(
        self,
        tolerance_minutes=None,
        table_prefix="",
        dry_run=False,
        heartbeat_timeout_seconds=120,
    ):
        self.tolerance_minutes = tolerance_minutes
        self.table_prefix = table_prefix
        self.dry_run = dry_run

        if heartbeat_timeout_seconds <= 0:
            raise ValueError("Heartbeat timeout must be positive")
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds

        self._stop_event = Event()
        self._thread = None
        self._lock = Lock()

        self._last_heartbeat = monotonic()
        self._last_successful_end = None

        self._status = {
            "phase": "stopped",
            "counts": None,
            "error": None,
            "next_run_at": None,
        }

    def start(self, interval_minutes):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False

            self._stop_event.clear()
            self._last_heartbeat = monotonic()
            self._status["phase"] = "fetching"
            self._status["error"] = None
            self._status["next_run_at"] = None

            self._thread = Thread(
                target=self._loop,
                args=(interval_minutes,),
                name="AIS polling worker",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self):
        with self._lock:
            self._stop_event.set()

    def _loop(self, interval_minutes):
        interval_seconds = interval_minutes * 60
        retry_start = None

        try:
            while not self._stop_event.is_set():
                if self._heartbeat_expired():
                    self._stop_event.set()
                    break

                with self._lock:
                    self._status["phase"] = "fetching"
                    self._status["next_run_at"] = None

                started = monotonic()
                window = None

                try:
                    window = build_time_window(
                        interval_minutes,
                        self.tolerance_minutes,
                    )

                    overlap = (
                        window["fin"] - window["ini"]
                        - timedelta(minutes=interval_minutes)
                    )

                    if retry_start is not None:
                        window["ini"] = retry_start
                    elif self._last_successful_end is not None:
                        window["ini"] = self._last_successful_end - overlap

                    counts = run_once(
                        window,
                        table_prefix=self.table_prefix,
                        dry_run=self.dry_run,
                    )

                    
                    retry_start = None

                    with self._lock:
                        self._last_successful_end = window["fin"]
                        self._status["counts"] = counts
                        self._status["error"] = None

                except Exception as error:
                    if window is not None:
                        retry_start = window["ini"]

                    with self._lock:
                        self._status["error"] = str(error)

                remaining = interval_seconds - (monotonic() - started)
                wait_seconds = remaining if remaining > 0 else interval_seconds
                next_run_at = wait_seconds + monotonic()

                with self._lock:
                    self._status["phase"] = "waiting"
                    self._status["next_run_at"] = next_run_at

                if self._wait_for_next_run(next_run_at):
                    break

        finally:
            with self._lock:
                self._status["phase"] = "stopped"
                self._status["next_run_at"] = None

    def status(self):
        with self._lock:
            snapshot = self._status.copy()

            if snapshot["phase"] == "fetching" and self._stop_event.is_set():
                snapshot["phase"] = "stopping"

            snapshot["last_successful_end"] = self._last_successful_end

            if snapshot["counts"] is not None:
                snapshot["counts"] = snapshot["counts"].copy()

            return snapshot


    def heartbeat(self):
        with self._lock:
            self._last_heartbeat = monotonic()


    def _heartbeat_expired(self):
        with self._lock:
            age = monotonic() - self._last_heartbeat
            return age >= self.heartbeat_timeout_seconds


    def _wait_for_next_run(self, deadline):

        while not self._stop_event.is_set():
            if self._heartbeat_expired():
                self._stop_event.set()
                return True

            remaining = deadline - monotonic()
            if remaining <= 0:
                return False

            if self._stop_event.wait(min(1.0, remaining)):
                return True

        return True

polling_worker = PollingWorker()