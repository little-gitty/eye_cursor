"""Hosted API for accounts, device pairing, settings, and liveness."""

from __future__ import annotations

import hashlib
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from supabase import Client, create_client


load_dotenv(Path(__file__).with_name(".env"))

app = FastAPI(title="Eye Mouse Cloud API", version="1.0.0")
allowed_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:4173",
    ).split(",")
    if origin.strip().rstrip("/")
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

bearer = HTTPBearer(auto_error=False)


class DeviceSettings(BaseModel):
    yaw_range_degrees: float = Field(default=20.0, ge=5.0, le=60.0)
    pitch_range_degrees: float = Field(default=15.0, ge=5.0, le=45.0)
    smoothing_window: int = Field(default=8, ge=1, le=24)
    pose_smoothing_alpha: float = Field(default=0.35, ge=0.05, le=1.0)


class PairingRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)
    label: str = Field(default="Windows computer", min_length=1, max_length=80)


class DeviceRegistrationRequest(BaseModel):
    label: str = Field(default="Windows computer", min_length=1, max_length=80)


class DeviceStatus(BaseModel):
    face_detected: bool = False
    mouse_enabled: bool = False
    yaw: float | None = None
    pitch: float | None = None
    fps: float | None = Field(default=None, ge=0.0, le=240.0)
    message: str = Field(default="", max_length=100)


class PairingCodeResponse(BaseModel):
    code: str
    expires_at: datetime


@lru_cache(maxsize=1)
def admin_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cloud API is not configured. Set Supabase environment variables.",
        )
    return create_client(url, service_key)


def user_id_from_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Sign in to continue.")

    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    if not supabase_url or not anon_key:
        raise HTTPException(status_code=503, detail="Cloud API is not configured.")

    try:
        response = httpx.get(
            f"{supabase_url.rstrip('/')}/auth/v1/user",
            headers={"apikey": anon_key, "Authorization": f"Bearer {credentials.credentials}"},
            timeout=8.0,
        )
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Could not verify account session.") from error
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Your session has expired.")
    user = response.json()
    if not user.get("id"):
        raise HTTPException(status_code=401, detail="Invalid account session.")
    return str(user["id"])


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ensure_database_schema() -> None:
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not service_key:
        return

    required_tables = ("eye_devices", "eye_pairing_codes")
    try:
        for table_name in required_tables:
            admin_client().table(table_name).select("id").limit(1).execute()
    except Exception as exc:  # pragma: no cover - exercised through integration environment
        raise RuntimeError(
            "Cloud database is not initialized. Open the Supabase SQL editor and run backend/schema.sql, "
            "then restart the API."
        ) from exc


@app.on_event("startup")
def startup() -> None:
    ensure_database_schema()


def device_for_token(device_id: str, token: str) -> dict[str, Any]:
    result = (
        admin_client()
        .table("eye_devices")
        .select("id,user_id,label,settings,status,last_seen_at")
        .eq("id", device_id)
        .eq("token_hash", hash_secret(token))
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=401, detail="Device token is invalid or revoked.")
    return result.data[0]


def agent_device(
    device_id: str,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Device authentication required.")
    return device_for_token(device_id, credentials.credentials)


def owned_device(device_id: str, user_id: str) -> dict[str, Any]:
    result = (
        admin_client()
        .table("eye_devices")
        .select("id,user_id,label,settings,status,created_at,last_seen_at")
        .eq("id", device_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Device not found.")
    return result.data[0]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "eye-mouse-cloud"}


@app.post("/v1/camera/open")
def open_camera(user_id: str = Depends(user_id_from_auth)) -> dict[str, str]:
    if os.getenv("RENDER") == "true" or os.getenv("RENDER_EXTERNAL_URL"):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "A cloud deployment cannot open a camera on your computer. "
                "Start Eye Mouse using the local Windows launcher."
            ),
        )

    project_root = Path(__file__).resolve().parents[1]
    launcher_path = project_root / "launcher.py"
    if not launcher_path.exists():
        raise HTTPException(status_code=500, detail="Camera launcher is missing on this machine.")

    python_executables = (
        project_root / ".venv" / "Scripts" / "pythonw.exe",
        Path(sys.executable).with_name("pythonw.exe"),
    )
    python_executable = next(
        (candidate for candidate in python_executables if candidate.exists()),
        Path(sys.executable),
    )

    launch_kwargs: dict[str, Any] = {"cwd": str(project_root)}
    if os.name == "nt":
        launch_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        launch_kwargs["start_new_session"] = True

    try:
        subprocess.Popen([str(python_executable), str(launcher_path)], **launch_kwargs)
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"Could not start camera launcher: {error}") from error
    return {"status": "opened", "launcher": str(launcher_path)}


@app.post("/v1/pairing-codes", response_model=PairingCodeResponse)
def create_pairing_code(user_id: str = Depends(user_id_from_auth)) -> PairingCodeResponse:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    admin_client().table("eye_pairing_codes").insert({
        "user_id": user_id,
        "code_hash": hash_secret(code),
        "expires_at": expires_at.isoformat(),
    }).execute()
    return PairingCodeResponse(code=code, expires_at=expires_at)


@app.post("/v1/devices/pair")
def redeem_pairing_code(request: PairingRequest) -> dict[str, Any]:
    claimed = admin_client().rpc(
        "consume_eye_pairing_code",
        {"p_code_hash": hash_secret(request.code.strip().upper())},
    ).execute()
    owner_id = claimed.data
    if not owner_id:
        raise HTTPException(status_code=400, detail="Pairing code is invalid, expired, or already used.")

    token = secrets.token_urlsafe(36)
    settings = DeviceSettings().model_dump()
    inserted = admin_client().table("eye_devices").insert({
        "user_id": owner_id,
        "label": request.label.strip(),
        "token_hash": hash_secret(token),
        "settings": settings,
        "status": {"connected": False, "face_detected": False, "mouse_enabled": False},
    }).execute()
    device = inserted.data[0]
    return {"device_id": device["id"], "device_token": token, "settings": settings}


@app.post("/v1/devices/self")
def register_self_device(
    request: DeviceRegistrationRequest,
    user_id: str = Depends(user_id_from_auth),
) -> dict[str, Any]:
    device_label = request.label.strip() or "Windows computer"
    token = secrets.token_urlsafe(36)
    settings = DeviceSettings().model_dump()
    inserted = admin_client().table("eye_devices").insert({
        "user_id": user_id,
        "label": device_label[:80],
        "token_hash": hash_secret(token),
        "settings": settings,
        "status": {"connected": False, "face_detected": False, "mouse_enabled": False},
    }).execute()
    device = inserted.data[0]
    return {"device_id": device["id"], "device_token": token, "settings": settings}


@app.get("/v1/devices")
def list_devices(user_id: str = Depends(user_id_from_auth)) -> list[dict[str, Any]]:
    result = (
        admin_client()
        .table("eye_devices")
        .select("id,label,settings,status,created_at,last_seen_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


@app.get("/v1/devices/{device_id}/settings")
def get_device_settings(
    device_id: str,
    device: dict[str, Any] = Depends(agent_device),
) -> dict[str, Any]:
    return {"settings": device["settings"]}


@app.patch("/v1/devices/{device_id}/settings")
def update_device_settings(
    device_id: str,
    settings: DeviceSettings,
    user_id: str = Depends(user_id_from_auth),
) -> dict[str, Any]:
    owned_device(device_id, user_id)
    result = (
        admin_client()
        .table("eye_devices")
        .update({"settings": settings.model_dump()})
        .eq("id", device_id)
        .eq("user_id", user_id)
        .execute()
    )
    return {"settings": result.data[0]["settings"]}


@app.post("/v1/devices/{device_id}/status")
def update_device_status(
    device_id: str,
    device_status: DeviceStatus,
    device: dict[str, Any] = Depends(agent_device),
) -> dict[str, bool]:
    admin_client().table("eye_devices").update({
        "status": {**device_status.model_dump(), "connected": True},
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", device_id).execute()
    return {"ok": True}


@app.delete("/v1/devices/{device_id}", status_code=204, response_class=Response)
def remove_device(device_id: str, user_id: str = Depends(user_id_from_auth)) -> Response:
    owned_device(device_id, user_id)
    admin_client().table("eye_devices").delete().eq("id", device_id).eq("user_id", user_id).execute()
    return Response(status_code=204)
