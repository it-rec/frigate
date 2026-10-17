"""Recording window used by the review description processor."""

import unittest
from unittest.mock import MagicMock

from frigate.config.camera.review import ImageSourceEnum
from frigate.data_processing.post.review_descriptions import (
    ReviewDescriptionProcessor,
)
from frigate.data_processing.types import PostProcessDataEnum


class TestReviewDescriptionWindow(unittest.TestCase):
    def test_recording_buffer_does_not_mutate_review(self) -> None:
        processor = ReviewDescriptionProcessor.__new__(ReviewDescriptionProcessor)
        processor.metrics = MagicMock()
        processor.review_desc_dps = MagicMock()
        processor.genai_manager = MagicMock()

        camera_config = MagicMock()
        camera_config.review.genai.enabled = True
        camera_config.review.genai.alerts = True
        camera_config.review.genai.debug_save_thumbnails = False
        camera_config.review.genai.image_source = ImageSourceEnum.recordings
        processor.config = MagicMock()
        processor.config.cameras.get.return_value = camera_config

        processor.get_recording_frames = MagicMock(return_value=[b"frame"])
        processor.start_analysis = MagicMock()

        final_data = {
            "id": "review-1",
            "camera": "front_door",
            "severity": "alert",
            "start_time": 100.0,
            "end_time": 130.0,
            "thumb_path": "/tmp/thumb.webp",
        }

        processor.process_data(
            {"type": "end", "after": final_data},
            PostProcessDataEnum.review,
        )

        # the frame window is buffered, the review itself is not
        args = processor.get_recording_frames.call_args.args
        self.assertLess(args[1], 100.0)
        self.assertGreater(args[2], 130.0)
        self.assertEqual(final_data["start_time"], 100.0)
        self.assertEqual(final_data["end_time"], 130.0)

        analyzed = processor.start_analysis.call_args.args[1]
        self.assertEqual(analyzed["start_time"], 100.0)
        self.assertEqual(analyzed["end_time"], 130.0)


if __name__ == "__main__":
    unittest.main()
