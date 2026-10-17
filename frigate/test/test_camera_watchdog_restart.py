"""Tests for pacing restarts of exited non-detect ffmpeg processes."""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from frigate.config import FrigateConfig
from frigate.config.camera.ffmpeg import CameraRoleEnum
from frigate.video.ffmpeg import CameraWatchdog


def build_watchdog() -> CameraWatchdog:
    config = FrigateConfig(
        **{
            "mqtt": {"host": "mqtt"},
            "cameras": {
                "front_door": {
                    "ffmpeg": {
                        "inputs": [
                            {
                                "path": "rtsp://10.0.0.1:554/video",
                                "roles": ["record"],
                            },
                            {
                                "path": "rtsp://10.0.0.1:554/video2",
                                "roles": ["detect"],
                            },
                        ],
                    },
                    "detect": {"width": 1280, "height": 720},
                    "record": {"enabled": True},
                }
            },
        }
    )
    with (
        patch("frigate.video.ffmpeg.LogPipe"),
        patch("frigate.video.ffmpeg.InterProcessRequestor"),
        patch("frigate.video.ffmpeg.RecordingsDataSubscriber"),
        patch("frigate.video.ffmpeg.CameraConfigUpdateSubscriber"),
    ):
        return CameraWatchdog(
            config.cameras["front_door"],
            1,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )


def build_exited_process(start_time: float, roles=None) -> dict:
    process = MagicMock()
    process.poll.return_value = 1
    return {
        "cmd": ["ffmpeg"],
        "roles": roles or [CameraRoleEnum.record],
        "logpipe": MagicMock(),
        "process": process,
        "start_time": start_time,
    }


class TestExitedProcessRestart(unittest.TestCase):
    @patch("frigate.video.ffmpeg.start_or_restart_ffmpeg")
    def test_long_running_process_is_restarted_immediately(self, mock_start):
        watchdog = build_watchdog()
        now = datetime.now().timestamp()
        p = build_exited_process(now - 3600)

        watchdog._restart_exited_process(p, now)

        mock_start.assert_called_once()
        assert p["process"] is mock_start.return_value
        assert p["start_time"] == now

    @patch("frigate.video.ffmpeg.start_or_restart_ffmpeg")
    def test_exited_process_waits_for_retry_interval(self, mock_start):
        watchdog = build_watchdog()
        now = datetime.now().timestamp()
        p = build_exited_process(now - 3600)

        watchdog._restart_exited_process(p, now)
        assert mock_start.call_count == 1

        # the restarted process exits right away again
        for elapsed in range(1, int(watchdog.sleeptime)):
            watchdog._restart_exited_process(p, now + elapsed)
        assert mock_start.call_count == 1

        watchdog._restart_exited_process(p, now + watchdog.sleeptime)
        assert mock_start.call_count == 2

    @patch("frigate.video.ffmpeg.start_or_restart_ffmpeg")
    def test_restart_counts_as_reconnect(self, mock_start):
        watchdog = build_watchdog()
        now = datetime.now().timestamp()
        p = build_exited_process(now - 3600)

        watchdog._restart_exited_process(p, now)
        watchdog._restart_exited_process(p, now + 1)
        assert len(watchdog.reconnect_timestamps) == 1
        assert watchdog.reconnects.value == 1

        watchdog._restart_exited_process(p, now + watchdog.sleeptime)
        assert len(watchdog.reconnect_timestamps) == 2

    @patch("frigate.video.ffmpeg.start_or_restart_ffmpeg")
    def test_exit_is_reported_once_while_waiting(self, mock_start):
        watchdog = build_watchdog()
        now = datetime.now().timestamp()
        p = build_exited_process(now - 1, roles=[CameraRoleEnum.audio])

        for elapsed in range(0, int(watchdog.sleeptime) - 1):
            watchdog._restart_exited_process(p, now + elapsed)

        mock_start.assert_not_called()
        offline_calls = [
            c
            for c in watchdog.requestor.send_data.call_args_list
            if c.args == ("front_door/status/audio", "offline")
        ]
        assert len(offline_calls) == 1


if __name__ == "__main__":
    unittest.main(verbosity=2)
