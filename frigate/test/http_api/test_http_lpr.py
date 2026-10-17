"""Tests for the license plate library APIs."""

from frigate.models import Event, Recordings, ReviewSegment
from frigate.test.http_api.base_http_test import AuthTestClient, BaseTestHttp


class TestHttpLpr(BaseTestHttp):
    def setUp(self):
        super().setUp([Event, Recordings, ReviewSegment])
        self.minimal_config["lpr"] = {
            "enabled": True,
            "known_plates": {"My Car": ["ABC123"], "Delivery": ["DHL.*"]},
        }
        self.app = super().create_app()

    def _insert_plate_event(
        self, id: str, plate: str, start_time: float, score: float = 0.9
    ) -> None:
        self.insert_mock_event(
            id,
            start_time=start_time,
            data={
                "recognized_license_plate": plate,
                "recognized_license_plate_score": score,
            },
        )

    def test_plates_returns_summaries(self):
        self._insert_plate_event("event_1", "ABC123", 1000, score=0.7)
        self._insert_plate_event("event_2", "ABC123", 2000, score=0.9)
        self._insert_plate_event("event_3", "XYZ789", 1500, score=0.8)
        # event without plate data is ignored
        self.insert_mock_event("event_4", start_time=2500)

        with AuthTestClient(self.app) as client:
            response = client.get("/lpr/plates")

        assert response.status_code == 200
        summaries = {item["plate"]: item for item in response.json()}
        assert set(summaries.keys()) == {"ABC123", "XYZ789"}

        abc = summaries["ABC123"]
        assert abc["count"] == 2
        assert abc["latest_event_id"] == "event_2"
        assert abc["latest_time"] == 2000
        assert abc["best_score"] == 0.9
        assert abc["cameras"] == ["front_door"]
        assert abc["known_name"] == "My Car"

        assert summaries["XYZ789"]["known_name"] is None

    def test_plates_matches_known_plate_regex(self):
        self._insert_plate_event("event_1", "DHL4711", 1000)

        with AuthTestClient(self.app) as client:
            response = client.get("/lpr/plates")

        assert response.status_code == 200
        assert response.json()[0]["known_name"] == "Delivery"

    def test_plates_requires_admin(self):
        with AuthTestClient(self.app) as client:
            response = client.get(
                "/lpr/plates",
                headers={"remote-user": "viewer", "remote-role": "viewer"},
            )

        assert response.status_code == 403

    def test_plates_requires_lpr_enabled(self):
        self.minimal_config["lpr"] = {"enabled": False}
        app = super().create_app()

        with AuthTestClient(app) as client:
            response = client.get("/lpr/plates")

        assert response.status_code == 400
