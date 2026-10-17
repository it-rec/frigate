"""Tests for per stream recording health tracking in the camera watchdog."""

import subprocess as sp
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, call, patch

from frigate.config import FrigateConfig
from frigate.config.camera.ffmpeg import CameraRoleEnum
from frigate.const import STREAM_TYPE_MAIN, STREAM_TYPE_SUB
from frigate.video.ffmpeg import CameraWatchdog


def build_watchdog(
    sub_enabled: bool = True, output_args: dict | None = None
) -> CameraWatchdog:
    config = FrigateConfig(
        **{
            "mqtt": {"host": "mqtt"},
            "cameras": {
                "front_door": {
                    "ffmpeg": {
                        "output_args": output_args or {},
                        "inputs": [
                            {
                                "path": "rtsp://10.0.0.1:554/video",
                                "roles": ["record"],
                            },
                            {
                                "path": "rtsp://10.0.0.1:554/video2",
                                "roles": ["detect", "record_sub"],
                            },
                        ],
                    },
                    "record": {
                        "enabled": True,
                        "sub": {"enabled": sub_enabled},
                    },
                }
            },
        }
    )
    camera_config = config.cameras["front_door"]

    with (
        patch("frigate.video.ffmpeg.LogPipe"),
        patch("frigate.video.ffmpeg.InterProcessRequestor"),
        patch("frigate.video.ffmpeg.RecordingsDataSubscriber"),
        patch("frigate.video.ffmpeg.CameraConfigUpdateSubscriber"),
    ):
        watchdog = CameraWatchdog(
            camera_config,
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

    return watchdog


class TestCameraWatchdogReset(unittest.TestCase):
    def _build_resettable_watchdog(self) -> CameraWatchdog:
        watchdog = build_watchdog()
        watchdog.ffmpeg_detect_process = MagicMock()
        watchdog.capture_thread = MagicMock()
        watchdog.capture_thread.is_alive.return_value = False
        watchdog.start_ffmpeg_detect = MagicMock()
        return watchdog

    def test_reset_does_not_buffer_raw_frames(self):
        watchdog = self._build_resettable_watchdog()
        process = watchdog.ffmpeg_detect_process

        watchdog.reset_capture_thread()

        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=30)
        process.communicate.assert_not_called()
        watchdog.start_ffmpeg_detect.assert_called_once()

    def test_timed_out_reset_kills_and_reaps_without_reading_stdout(self):
        watchdog = self._build_resettable_watchdog()
        process = watchdog.ffmpeg_detect_process
        process.wait.side_effect = [sp.TimeoutExpired("ffmpeg", 30), 0]

        watchdog.reset_capture_thread()

        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_args_list, [call(timeout=30), call()])
        process.communicate.assert_not_called()
        watchdog.start_ffmpeg_detect.assert_called_once()


class TestCameraWatchdogStreamHealth(unittest.TestCase):
    def _build_watchdog(
        self, sub_enabled: bool = True, output_args: dict | None = None
    ) -> CameraWatchdog:
        return build_watchdog(sub_enabled, output_args)

    def test_stale_sub_does_not_mark_main_stale(self):
        watchdog = self._build_watchdog()
        now = datetime.now().astimezone(UTC)
        stale = (now - timedelta(hours=1)).timestamp()

        watchdog.latest_cache_segment_time[STREAM_TYPE_MAIN] = now.timestamp()
        watchdog.latest_valid_segment_time[STREAM_TYPE_MAIN] = now.timestamp()
        watchdog.latest_cache_segment_time[STREAM_TYPE_SUB] = stale
        watchdog.latest_valid_segment_time[STREAM_TYPE_SUB] = stale

        assert watchdog._stream_staleness(STREAM_TYPE_MAIN, now) is None
        assert watchdog._stream_staleness(STREAM_TYPE_SUB, now) is not None

    def test_stale_main_does_not_mark_sub_stale(self):
        watchdog = self._build_watchdog()
        now = datetime.now().astimezone(UTC)
        stale = (now - timedelta(hours=1)).timestamp()

        watchdog.latest_cache_segment_time[STREAM_TYPE_MAIN] = stale
        watchdog.latest_valid_segment_time[STREAM_TYPE_MAIN] = stale
        watchdog.latest_cache_segment_time[STREAM_TYPE_SUB] = now.timestamp()
        watchdog.latest_valid_segment_time[STREAM_TYPE_SUB] = now.timestamp()

        assert watchdog._stream_staleness(STREAM_TYPE_MAIN, now) is not None
        assert watchdog._stream_staleness(STREAM_TYPE_SUB, now) is None

    def test_grace_period_suppresses_staleness(self):
        watchdog = self._build_watchdog()
        now = datetime.now().astimezone(UTC)
        watchdog.record_enable_time = now - timedelta(seconds=10)
        watchdog.latest_cache_segment_time[STREAM_TYPE_SUB] = (
            now - timedelta(hours=1)
        ).timestamp()

        assert watchdog._stream_staleness(STREAM_TYPE_SUB, now) is None

    def test_status_goes_to_the_matching_role_topic(self):
        watchdog = self._build_watchdog()

        watchdog.record_status[STREAM_TYPE_MAIN].send("online", 100.0)
        watchdog.record_status[STREAM_TYPE_SUB].send("offline", 100.0)

        watchdog.requestor.send_data.assert_any_call(
            "front_door/status/record", "online"
        )
        watchdog.requestor.send_data.assert_any_call(
            "front_door/status/record_sub", "offline"
        )

    def test_status_is_cached_per_stream(self):
        watchdog = self._build_watchdog()

        watchdog.record_status[STREAM_TYPE_MAIN].send("online", 100.0)
        watchdog.record_status[STREAM_TYPE_SUB].send("online", 100.0)
        watchdog.record_status[STREAM_TYPE_MAIN].send("online", 100.0)

        assert watchdog.requestor.send_data.call_count == 2

    def test_recorded_streams_follows_config(self):
        watchdog = self._build_watchdog()
        assert watchdog._recorded_streams(["record"]) == [STREAM_TYPE_MAIN]
        assert watchdog._recorded_streams(["detect", "record_sub"]) == [STREAM_TYPE_SUB]
        assert watchdog._recorded_streams(["detect"]) == []

        disabled = self._build_watchdog(sub_enabled=False)
        assert disabled._recorded_streams(["detect", "record_sub"]) == []

    def test_restart_grace_suppresses_repeat_staleness(self):
        watchdog = self._build_watchdog()
        now = datetime.now().astimezone(UTC)
        stale = (now - timedelta(hours=1)).timestamp()

        watchdog.latest_cache_segment_time[STREAM_TYPE_MAIN] = stale
        watchdog.latest_valid_segment_time[STREAM_TYPE_MAIN] = stale
        assert watchdog._stream_staleness(STREAM_TYPE_MAIN, now) is not None

        watchdog._grant_restart_grace([STREAM_TYPE_MAIN], now)

        assert watchdog._stream_staleness(STREAM_TYPE_MAIN, now) is None
        assert (
            watchdog._stream_staleness(STREAM_TYPE_MAIN, now + timedelta(seconds=89))
            is None
        )
        assert (
            watchdog._stream_staleness(STREAM_TYPE_MAIN, now + timedelta(seconds=91))
            is not None
        )

    def test_restart_grace_is_per_stream(self):
        watchdog = self._build_watchdog()
        now = datetime.now().astimezone(UTC)
        stale = (now - timedelta(hours=1)).timestamp()

        for stream_type in (STREAM_TYPE_MAIN, STREAM_TYPE_SUB):
            watchdog.latest_cache_segment_time[stream_type] = stale
            watchdog.latest_valid_segment_time[stream_type] = stale

        watchdog._grant_restart_grace([STREAM_TYPE_MAIN], now)

        assert watchdog._stream_staleness(STREAM_TYPE_MAIN, now) is None
        assert watchdog._stream_staleness(STREAM_TYPE_SUB, now) is not None

    def test_detect_reset_grants_the_shared_sub_stream_grace(self):
        watchdog = self._build_watchdog()
        watchdog.detect_process_records_sub = True
        watchdog.ffmpeg_detect_process = MagicMock()
        watchdog.capture_thread = MagicMock()
        watchdog.capture_thread.is_alive.return_value = False
        watchdog.start_ffmpeg_detect = MagicMock()

        now = datetime.now().astimezone(UTC)
        stale = (now - timedelta(hours=1)).timestamp()
        watchdog.latest_cache_segment_time[STREAM_TYPE_SUB] = stale
        watchdog.latest_valid_segment_time[STREAM_TYPE_SUB] = stale
        assert watchdog._stream_staleness(STREAM_TYPE_SUB, now) is not None

        watchdog.reset_capture_thread(terminate=False)

        # the sub check runs later in the same tick against a stale can_restart,
        # so without this grace it would kill the just-restarted process again
        assert (
            watchdog._stream_staleness(STREAM_TYPE_SUB, datetime.now().astimezone(UTC))
            is None
        )

    def test_detect_reset_leaves_sub_alone_when_not_shared(self):
        watchdog = self._build_watchdog()
        watchdog.detect_process_records_sub = False
        watchdog.ffmpeg_detect_process = MagicMock()
        watchdog.capture_thread = MagicMock()
        watchdog.capture_thread.is_alive.return_value = False
        watchdog.start_ffmpeg_detect = MagicMock()

        now = datetime.now().astimezone(UTC)
        stale = (now - timedelta(hours=1)).timestamp()
        watchdog.latest_cache_segment_time[STREAM_TYPE_SUB] = stale
        watchdog.latest_valid_segment_time[STREAM_TYPE_SUB] = stale

        watchdog.reset_capture_thread(terminate=False)

        assert (
            watchdog._stream_staleness(STREAM_TYPE_SUB, datetime.now().astimezone(UTC))
            is not None
        )

    def test_stale_threshold_follows_each_stream_segment_time(self):
        watchdog = self._build_watchdog(
            output_args={
                "record": "-f segment -segment_time 10 -c copy",
                "record_sub": "-f segment -segment_time 60 -c copy",
            }
        )

        assert watchdog.record_stale_threshold[STREAM_TYPE_MAIN] == 120
        assert watchdog.record_stale_threshold[STREAM_TYPE_SUB] == 150


class TestCameraWatchdogExitedProcessRestart(unittest.TestCase):
    def _build_exited_process(self, start_time: float) -> dict:
        process = MagicMock()
        process.poll.return_value = 1
        return {
            "cmd": ["ffmpeg"],
            "roles": [CameraRoleEnum.record],
            "logpipe": MagicMock(),
            "process": process,
            "start_time": start_time,
        }

    @patch("frigate.video.ffmpeg.start_or_restart_ffmpeg")
    def test_long_running_process_is_restarted_immediately(self, mock_start):
        watchdog = build_watchdog()
        now = datetime.now().timestamp()
        p = self._build_exited_process(now - 3600)

        watchdog._restart_exited_process(p, now)

        mock_start.assert_called_once()
        assert p["process"] is mock_start.return_value
        assert p["start_time"] == now
        watchdog.requestor.send_data.assert_any_call(
            "front_door/status/record", "offline"
        )

    @patch("frigate.video.ffmpeg.start_or_restart_ffmpeg")
    def test_exited_process_waits_for_retry_interval(self, mock_start):
        watchdog = build_watchdog()
        now = datetime.now().timestamp()
        p = self._build_exited_process(now - 3600)

        watchdog._restart_exited_process(p, now)
        assert mock_start.call_count == 1

        # the restarted process exits right away again
        for elapsed in range(1, int(watchdog.sleeptime)):
            watchdog._restart_exited_process(p, now + elapsed)

        assert mock_start.call_count == 1

        watchdog._restart_exited_process(p, now + watchdog.sleeptime)
        assert mock_start.call_count == 2

    @patch("frigate.video.ffmpeg.start_or_restart_ffmpeg")
    def test_exit_is_reported_once_while_waiting(self, mock_start):
        watchdog = build_watchdog()
        now = datetime.now().timestamp()
        p = self._build_exited_process(now - 1)
        p["roles"] = [CameraRoleEnum.audio]

        for elapsed in range(0, int(watchdog.sleeptime) - 1):
            watchdog._restart_exited_process(p, now + elapsed)

        mock_start.assert_not_called()
        offline_calls = [
            c
            for c in watchdog.requestor.send_data.call_args_list
            if c.args == ("front_door/status/audio", "offline")
        ]
        assert len(offline_calls) == 1

    @patch("frigate.video.ffmpeg.start_or_restart_ffmpeg")
    def test_exited_process_restart_counts_as_reconnect(self, mock_start):
        watchdog = build_watchdog()
        now = datetime.now().timestamp()
        p = self._build_exited_process(now - 3600)

        watchdog._restart_exited_process(p, now)
        watchdog._restart_exited_process(p, now + 1)

        assert len(watchdog.reconnect_timestamps) == 1
        assert watchdog.reconnects.value == 1

        watchdog._restart_exited_process(p, now + watchdog.sleeptime)

        assert len(watchdog.reconnect_timestamps) == 2
        assert watchdog.reconnects.value == 2
