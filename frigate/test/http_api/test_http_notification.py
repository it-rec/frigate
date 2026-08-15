"""Tests for the notification registration APIs."""

from frigate.models import Event, Recordings, ReviewSegment, User
from frigate.test.http_api.base_http_test import AuthTestClient, BaseTestHttp


class TestHttpNotification(BaseTestHttp):
    def setUp(self):
        super().setUp([Event, Recordings, ReviewSegment, User])
        self.app = super().create_app()
        self.sub = {"endpoint": "https://push.example.com/sub/1", "keys": {}}

        User.insert(
            username="admin",
            role="admin",
            password_hash="hash",
            notification_tokens=[],
        ).execute()
        User.insert(
            username="viewer",
            role="viewer",
            password_hash="hash",
            notification_tokens=[],
        ).execute()

    def test_register_attributes_token_to_authenticated_user(self):
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/notifications/register",
                json={"sub": self.sub},
                headers={"remote-user": "viewer", "remote-role": "viewer"},
            )

        assert response.status_code == 200
        viewer = User.get_by_id("viewer")
        admin = User.get_by_id("admin")
        assert viewer.notification_tokens == [self.sub]
        assert admin.notification_tokens == []

    def test_register_anonymous_internal_request_attributed_to_admin(self):
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/notifications/register",
                json={"sub": self.sub},
                headers={"remote-user": "anonymous", "remote-role": "admin"},
            )

        assert response.status_code == 200
        admin = User.get_by_id("admin")
        assert admin.notification_tokens == [self.sub]

    def test_register_unknown_user_returns_404(self):
        with AuthTestClient(self.app) as client:
            response = client.post(
                "/notifications/register",
                json={"sub": self.sub},
                headers={"remote-user": "ghost", "remote-role": "viewer"},
            )

        assert response.status_code == 404
        assert response.json()["success"] is False

    def test_register_without_subscription_returns_400(self):
        with AuthTestClient(self.app) as client:
            response = client.post("/notifications/register", json={})

        assert response.status_code == 400
