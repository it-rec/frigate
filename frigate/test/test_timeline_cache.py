"""Tests for TimelineProcessor pre_event_cache lifecycle."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from frigate.events.types import EventStateEnum
from frigate.timeline import TimelineProcessor


def _camera_config() -> SimpleNamespace:
    return SimpleNamespace(detect=SimpleNamespace(width=1920, height=1080))


def _event_data(
    event_id: str, has_clip: bool = False, has_snapshot: bool = False
) -> dict:
    return {
        "id": event_id,
        "frame_time": 1000.0,
        "box": [10, 10, 110, 110],
        "region": [0, 0, 200, 200],
        "label": "person",
        "sub_label": None,
        "score": 0.9,
        "has_clip": has_clip,
        "has_snapshot": has_snapshot,
    }


class TestTimelinePreEventCache(unittest.TestCase):
    def setUp(self) -> None:
        config = MagicMock()
        config.cameras.get.return_value = _camera_config()
        self.processor = TimelineProcessor(config, MagicMock(), MagicMock())

    def test_unsaved_event_is_evicted_on_end(self) -> None:
        event_id = "unsaved-1"

        # start buffers the entry because the event has no clip/snapshot yet
        self.processor.handle_object_detection(
            "front_door",
            EventStateEnum.start,
            None,
            _event_data(event_id),
        )
        self.assertIn(event_id, self.processor.pre_event_cache)

        # end for a still-unsaved event must drop the buffered entries so the
        # cache does not grow without bound
        self.processor.handle_object_detection(
            "front_door",
            EventStateEnum.end,
            _event_data(event_id),
            _event_data(event_id),
        )
        self.assertNotIn(event_id, self.processor.pre_event_cache)


if __name__ == "__main__":
    unittest.main()
