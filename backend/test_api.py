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

    def test_route_exposes_self_registration_endpoint(self):
        routes = {route.path for route in app.routes}
        self.assertIn("/v1/devices/self", routes)

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
