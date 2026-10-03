"""Optional cloud pairing and heartbeat client for the local Windows controller."""

from __future__ import annotations

import argparse
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PAIRING_TIMEOUT_SECONDS = 10
POLL_INTERVAL_SECONDS = 5


def credential_path() -> Path:
    base = Path(os.getenv("APPDATA", Path.home() / ".config"))
    return base / "EyeMouse" / "device.json"


def request_json(
    api_url: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}{path}",
        data=body,
        headers=headers,
        method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=PAIRING_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cloud API returned {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not contact cloud API: {error.reason}") from error


def pair_device(code: str, api_url: str, label: str) -> Path:
    result = request_json(
        api_url,
        "/v1/devices/pair",
        payload={"code": code.strip().upper(), "label": label},
    )
    target = credential_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({
            "api_url": api_url.rstrip("/"),
            "device_id": result["device_id"],
            "device_token": result["device_token"],
        }, indent=2),
        encoding="utf-8",
    )
    print(f"Paired successfully. Device credentials saved to {target}")
    print("The device token is stored locally and is never shown again.")
    return target


def sign_in_supabase(supabase_url: str, anon_key: str, email: str, password: str) -> str:
    payload = json.dumps({
        "email": email,
        "password": password,
        "grant_type": "password",
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{supabase_url.rstrip('/')}/auth/v1/token",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "apikey": anon_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=PAIRING_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase sign-in failed: {error.code}: {detail}") from error
    access_token = data.get("access_token")
    if not access_token:
        raise RuntimeError("Supabase sign-in response did not include an access token.")
    return str(access_token)


def register_local_device(api_url: str, supabase_url: str, anon_key: str, email: str, password: str, label: str) -> Path:
    token = sign_in_supabase(supabase_url, anon_key, email, password)
    result = request_json(
        api_url,
        "/v1/devices/self",
        token=token,
        payload={"label": label},
    )
    target = credential_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({
            "api_url": api_url.rstrip("/"),
            "device_id": result["device_id"],
            "device_token": result["device_token"],
        }, indent=2),
        encoding="utf-8",
    )
    print(f"Local device registered successfully. Credentials saved to {target}")
    print("The device token is stored locally and is never shown again.")
    return target


class CloudAgent:
    """Send status and receive settings without blocking camera processing."""

    def __init__(self, credentials: dict[str, str]) -> None:
        self.api_url = credentials["api_url"].rstrip("/")
        self.device_id = credentials["device_id"]
        self.device_token = credentials["device_token"]
        self.settings_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self.status_lock = threading.Lock()
        self.latest_status: dict[str, Any] = {}
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None

    @classmethod
    def from_saved_credentials(cls) -> CloudAgent | None:
        path = credential_path()
        if not path.is_file():
            return None
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if not all(saved.get(key) for key in ("api_url", "device_id", "device_token")):
                return None
            return cls(saved)
        except (OSError, json.JSONDecodeError, TypeError):
            return None

    def start(self) -> None:
        if self.worker is not None:
            return
        self.worker = threading.Thread(target=self._run, name="eye-mouse-cloud", daemon=True)
        self.worker.start()

    def update_status(self, status: dict[str, Any]) -> None:
        with self.status_lock:
            self.latest_status = status.copy()

    def take_settings(self) -> dict[str, Any] | None:
        try:
            return self.settings_queue.get_nowait()
        except queue.Empty:
            return None

    def close(self) -> None:
        self.stop_event.set()
        if self.worker is not None:
            self.worker.join(timeout=PAIRING_TIMEOUT_SECONDS + 1)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                response = request_json(
                    self.api_url,
                    f"/v1/devices/{self.device_id}/settings",
                    token=self.device_token,
                )
                settings = response.get("settings")
                if isinstance(settings, dict):
                    try:
                        self.settings_queue.put_nowait(settings)
                    except queue.Full:
                        try:
                            self.settings_queue.get_nowait()
                        except queue.Empty:
                            pass
                        self.settings_queue.put_nowait(settings)
                with self.status_lock:
                    current = self.latest_status.copy()
                request_json(
                    self.api_url,
                    f"/v1/devices/{self.device_id}/status",
                    token=self.device_token,
                    payload=current,
                )
            except RuntimeError as error:
                if "returned 401" in str(error) or "returned 404" in str(error):
                    self.stop_event.set()
                    return
            except (OSError, ValueError):
                pass
            self.stop_event.wait(POLL_INTERVAL_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pair this Windows Eye Mouse installation with its dashboard.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pair_parser = subparsers.add_parser("pair", help="Redeem a dashboard pairing code")
    pair_parser.add_argument("code", help="One-time code shown in the dashboard")
    pair_parser.add_argument("--api-url", required=True, help="Base URL of the Eye Mouse cloud API")
    pair_parser.add_argument("--label", default=os.getenv("COMPUTERNAME", "Windows computer"))

    register_parser = subparsers.add_parser("register", help="Register this local machine as a user-owned device")
    register_parser.add_argument("--api-url", required=True, help="Base URL of the Eye Mouse cloud API")
    register_parser.add_argument("--supabase-url", required=True, help="Supabase project URL, e.g. https://xyz.supabase.co")
    register_parser.add_argument("--supabase-anon-key", required=True, help="Supabase anon key from the project settings")
    register_parser.add_argument("--email", required=True, help="Account email for the signed-in user")
    register_parser.add_argument("--password", required=True, help="Account password for the signed-in user")
    register_parser.add_argument("--label", default=os.getenv("COMPUTERNAME", "Windows computer"))

    arguments = parser.parse_args()
    try:
        if arguments.command == "pair":
            pair_device(arguments.code, arguments.api_url, arguments.label)
        elif arguments.command == "register":
            register_local_device(
                arguments.api_url,
                arguments.supabase_url,
                arguments.supabase_anon_key,
                arguments.email,
                arguments.password,
                arguments.label,
            )
    except RuntimeError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
