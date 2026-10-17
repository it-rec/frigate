"""Temp file handling of the local whisper transcription path."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from frigate.data_processing.post.audio_transcription import (
    AudioTranscriptionPostProcessor,
)


class TestWhisperTempFile(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.patcher = patch(
            "frigate.data_processing.post.audio_transcription.CACHE_DIR",
            self.tmp.name,
        )
        self.patcher.start()

        self.processor = AudioTranscriptionPostProcessor.__new__(
            AudioTranscriptionPostProcessor
        )
        self.processor.config = MagicMock()
        self.processor.config.audio_transcription.language = "en"
        self.processor.recognizer = MagicMock()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.tmp.cleanup()

    def _transcribe(self) -> str | None:
        # name-mangled private method
        transcribe = getattr(
            self.processor, "_AudioTranscriptionPostProcessor__transcribe_audio_whisper"
        )
        return transcribe(b"RIFF....WAVE")

    def test_temp_wav_removed_when_transcribe_raises(self) -> None:
        self.processor.recognizer.transcribe.side_effect = RuntimeError("boom")

        self.assertIsNone(self._transcribe())
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_temp_wav_removed_after_success(self) -> None:
        segment = MagicMock()
        segment.text = " hello "
        self.processor.recognizer.transcribe.return_value = (
            [segment],
            MagicMock(language="en", language_probability=1.0),
        )

        self.assertEqual(self._transcribe(), "hello")
        self.assertEqual(os.listdir(self.tmp.name), [])


if __name__ == "__main__":
    unittest.main()
