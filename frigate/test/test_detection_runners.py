"""Tests for ONNX Runtime session option selection."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import onnxruntime as ort

from frigate.detectors.detection_runners import (
    CudaGraphRunner,
    OpenVINOModelRunner,
    get_ort_session_options,
)
from frigate.detectors.detector_config import ModelTypeEnum
from frigate.embeddings.types import EnrichmentModelTypeEnum


class TestGetOrtSessionOptions(unittest.TestCase):
    def test_jina_v2_uses_extended(self):
        """jina-clip-v2 returns an identical vector for every image on the CUDA
        execution provider at anything below EXTENDED."""
        options = get_ort_session_options(EnrichmentModelTypeEnum.jina_v2.value)

        self.assertIsNotNone(options)
        self.assertEqual(
            options.graph_optimization_level,
            ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED,
        )

    def test_jina_v1_uses_basic(self):
        options = get_ort_session_options(EnrichmentModelTypeEnum.jina_v1.value)

        self.assertIsNotNone(options)
        self.assertEqual(
            options.graph_optimization_level,
            ort.GraphOptimizationLevel.ORT_ENABLE_BASIC,
        )

    def test_other_models_use_defaults(self):
        for model_type in [
            None,
            EnrichmentModelTypeEnum.paddleocr.value,
            EnrichmentModelTypeEnum.arcface.value,
            ModelTypeEnum.rfdetr.value,
        ]:
            with self.subTest(model_type=model_type):
                self.assertIsNone(get_ort_session_options(model_type))


class TestCudaGraphRunner(unittest.TestCase):
    """CUDA graph capture fails if the arena has to allocate during capture, so
    the session is warmed up with capture disabled before the first real run."""

    def setUp(self):
        self.session = MagicMock()
        self.session.get_outputs.return_value = [MagicMock(name="output")]
        self.io_binding = self.session.io_binding.return_value
        self.input = {"images": np.zeros((1, 3, 320, 320), np.float32)}

    def _annotations(self) -> list[str | None]:
        """Graph annotation id passed with each run, None when unset."""
        annotations = []

        for call in self.session.run_with_iobinding.call_args_list:
            try:
                annotations.append(call.args[1].get_run_config_entry("gpu_graph_id"))
            except RuntimeError:
                annotations.append(None)

        return annotations

    def test_first_run_warms_up_with_capture_disabled(self):
        with patch.object(ort.OrtValue, "ortvalue_from_numpy"):
            CudaGraphRunner(self.session, 0).run(self.input)

        self.assertEqual(
            self._annotations(),
            ["-1"] * CudaGraphRunner.GRAPH_FREE_WARMUP_RUNS + [None],
        )

    def test_later_runs_allow_capture(self):
        with patch.object(ort.OrtValue, "ortvalue_from_numpy"):
            runner = CudaGraphRunner(self.session, 0)
            runner.run(self.input)
            self.session.run_with_iobinding.reset_mock()
            runner.run(self.input)

        self.assertEqual(self._annotations(), [None])
        runner._input_ortvalue.update_inplace.assert_called_once()


class TestOpenVINOModelCache(unittest.TestCase):
    """Compiled GPU/NPU models are cached so restarts skip kernel compilation."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache_root = tmp.name
        self.model_path = os.path.join(tmp.name, "model.onnx")
        open(self.model_path, "wb").close()

        self.ov = MagicMock()
        self.core = self.ov.Core.return_value
        for target, value in [
            ("frigate.detectors.detection_runners.ov", self.ov),
            ("frigate.detectors.detection_runners.MODEL_CACHE_DIR", self.cache_root),
        ]:
            patcher = patch(target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _cache_dirs(self) -> list[str]:
        return [
            call.args[0]["CACHE_DIR"]
            for call in self.core.set_property.call_args_list
            if len(call.args) == 1 and "CACHE_DIR" in call.args[0]
        ]

    def test_gpu_sets_cache_dir(self):
        OpenVINOModelRunner(self.model_path, "GPU", ModelTypeEnum.yologeneric.value)

        cache_dir = os.path.join(self.cache_root, "openvino/ov")
        self.assertEqual(self._cache_dirs(), [cache_dir])
        self.assertTrue(os.path.isdir(cache_dir))
        self.core.compile_model.assert_called_once()
        self.assertEqual(
            self.core.compile_model.call_args.kwargs["model"], self.model_path
        )

    def test_cpu_does_not_set_cache_dir(self):
        OpenVINOModelRunner(self.model_path, "CPU", ModelTypeEnum.yologeneric.value)

        self.assertEqual(self._cache_dirs(), [])

    def test_cache_failure_does_not_break_loading(self):
        def set_property(*args):
            if len(args) == 1 and "CACHE_DIR" in args[0]:
                raise RuntimeError("unsupported")

        self.core.set_property.side_effect = set_property

        runner = OpenVINOModelRunner(
            self.model_path, "GPU", ModelTypeEnum.yologeneric.value
        )

        self.core.compile_model.assert_called_once()
        self.assertIs(runner.compiled_model, self.core.compile_model.return_value)
