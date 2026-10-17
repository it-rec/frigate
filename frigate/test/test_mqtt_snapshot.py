"""Tests for when a tracked object's label snapshot is published over MQTT."""

import unittest
from unittest.mock import MagicMock

from frigate.track.object_processing import TrackedObjectProcessor


def _obj(false_positive: bool, stationary: bool = False, zones=None) -> MagicMock:
    obj = MagicMock()
    obj.false_positive = false_positive
    obj.is_stationary.return_value = stationary
    obj.entered_zones = zones or []
    obj.obj_data = {"id": "1234.5-abc"}
    return obj


def _mqtt_config(required_zones=None) -> MagicMock:
    config = MagicMock()
    config.required_zones = required_zones or []
    return config


class TestShouldMqttSnapshot(unittest.TestCase):
    def _should(self, obj, config) -> bool:
        return TrackedObjectProcessor.should_mqtt_snapshot(MagicMock(), config, obj)

    def test_unconfirmed_object_is_not_published(self):
        assert not self._should(_obj(false_positive=True), _mqtt_config())

    def test_confirmed_object_is_published(self):
        assert self._should(_obj(false_positive=False), _mqtt_config())

    def test_stationary_object_is_not_published(self):
        assert not self._should(
            _obj(false_positive=False, stationary=True), _mqtt_config()
        )

    def test_required_zones_still_apply(self):
        config = _mqtt_config(required_zones=["yard"])
        assert not self._should(_obj(false_positive=False), config)
        assert self._should(_obj(false_positive=False, zones=["yard"]), config)


if __name__ == "__main__":
    unittest.main(verbosity=2)
