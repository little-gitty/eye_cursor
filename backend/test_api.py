import os
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import main
from main import DeviceSettings, app


class CloudApiTests(unittest.TestCase):
    def test_health_endpoint_is_public(self):
        response = TestClient(app).get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_dashboard_preview_origin_passes_cors_preflight(self):
        response = TestClient(app).options(
            "/v1/devices",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:4173",
        )

    def test_route_exposes_self_registration_endpoint(self):
        routes = {route.path for route in app.routes}
        self.assertIn("/v1/devices/self", routes)

    def test_open_camera_endpoint_launches_local_launcher(self):
        original_popen = main.subprocess.Popen
        calls = {}

        def fake_popen(cmd, **kwargs):
            calls["cmd"] = cmd
            calls["cwd"] = kwargs.get("cwd")
            calls["creationflags"] = kwargs.get("creationflags")
            return object()

        main.subprocess.Popen = fake_popen
        try:
            response = TestClient(app).post("/v1/camera/open")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "opened")
            self.assertIn("launcher.py", calls["cmd"][-1])
            self.assertEqual(calls["cmd"][-1], str(Path(__file__).resolve().parents[1] / "launcher.py"))
            if os.name == "nt":
                self.assertEqual(calls["creationflags"], main.subprocess.CREATE_NO_WINDOW)
                self.assertNotEqual(calls["creationflags"], main.subprocess.CREATE_NEW_CONSOLE)
                expected_pythonw = Path(__file__).resolve().parents[1] / ".venv" / "Scripts" / "pythonw.exe"
                if not expected_pythonw.exists():
                    expected_pythonw = Path(main.sys.executable).with_name("pythonw.exe")
                expected_executable = expected_pythonw if expected_pythonw.exists() else Path(main.sys.executable)
                self.assertEqual(calls["cmd"][0], str(expected_executable))
        finally:
            main.subprocess.Popen = original_popen

    def test_open_camera_endpoint_rejects_cloud_deployment(self):
        original_render = os.environ.get("RENDER")
        original_render_url = os.environ.get("RENDER_EXTERNAL_URL")
        os.environ["RENDER"] = "true"
        os.environ.pop("RENDER_EXTERNAL_URL", None)
        try:
            response = TestClient(app).post("/v1/camera/open")
            self.assertEqual(response.status_code, 501)
            self.assertIn("cannot open a camera on your computer", response.json()["detail"])
        finally:
            if original_render is None:
                os.environ.pop("RENDER", None)
            else:
                os.environ["RENDER"] = original_render
            if original_render_url is None:
                os.environ.pop("RENDER_EXTERNAL_URL", None)
            else:
                os.environ["RENDER_EXTERNAL_URL"] = original_render_url

    def test_schema_sql_includes_required_tables(self):
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self.assertIn("create table if not exists public.eye_devices", schema.lower())
        self.assertIn("create table if not exists public.eye_pairing_codes", schema.lower())

    def test_database_bootstrap_reports_missing_schema(self):
        original_client = main.admin_client
        original_url = os.environ.get("SUPABASE_URL")
        original_service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        os.environ["SUPABASE_URL"] = "https://example.supabase.co"
        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-key"

        class FakeTable:
            def __init__(self, name: str):
                self.name = name

            def select(self, *_args, **_kwargs):
                return self

            def limit(self, *_args, **_kwargs):
                return self

            def execute(self):
                raise RuntimeError(f"relation \"{self.name}\" does not exist")

        class FakeClient:
            def table(self, name: str):
                return FakeTable(name)

        main.admin_client = lambda: FakeClient()
        try:
            with self.assertRaisesRegex(RuntimeError, "backend/schema.sql"):
                main.ensure_database_schema()
        finally:
            main.admin_client = original_client
            if original_url is None:
                os.environ.pop("SUPABASE_URL", None)
            else:
                os.environ["SUPABASE_URL"] = original_url
            if original_service_key is None:
                os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
            else:
                os.environ["SUPABASE_SERVICE_ROLE_KEY"] = original_service_key

    def test_settings_reject_unsafe_ranges(self):
        with self.assertRaises(ValueError):
            DeviceSettings(yaw_range_degrees=100)
        with self.assertRaises(ValueError):
            DeviceSettings(smoothing_window=0)

    def test_settings_accept_supported_values(self):
        settings = DeviceSettings(
            yaw_range_degrees=25,
            pitch_range_degrees=18,
            smoothing_window=10,
            pose_smoothing_alpha=0.4,
        )
        self.assertEqual(settings.smoothing_window, 10)


if __name__ == "__main__":
    unittest.main()
