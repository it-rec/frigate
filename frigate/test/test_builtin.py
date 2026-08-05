"""Tests for frigate.util.builtin helpers."""

import os
import unittest
from unittest.mock import patch

from frigate.util.builtin import EventsPerSecond, sanitized_subpath


class TestSanitizedSubpath(unittest.TestCase):
    def test_normal_name_stays_within_base(self) -> None:
        result = sanitized_subpath("/media/frigate/clips", "front_door")
        self.assertEqual(result, os.path.join("/media/frigate/clips", "front_door"))

    def test_multiple_parts(self) -> None:
        result = sanitized_subpath("/base", "model", "dataset", "cat")
        self.assertEqual(result, os.path.join("/base", "model", "dataset", "cat"))

    def test_parent_traversal_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            sanitized_subpath("/media/frigate/clips", "..")

    def test_current_dir_is_rejected(self) -> None:
        # "." resolves to the base directory itself, which would let rmtree
        # remove the base rather than a child.
        with self.assertRaises(ValueError):
            sanitized_subpath("/media/frigate/clips", ".")

    def test_separators_are_stripped_not_traversed(self) -> None:
        # sanitize_filename removes separators, so this collapses to a single
        # (odd but contained) component rather than escaping the base.
        result = sanitized_subpath("/base", "../../etc/passwd")
        self.assertTrue(os.path.realpath(result).startswith(os.path.realpath("/base")))


class TestEventsPerSecond(unittest.TestCase):
    def test_eps_is_zero_before_any_events(self) -> None:
        eps = EventsPerSecond()
        with patch("frigate.util.builtin.time.monotonic", return_value=100.0):
            self.assertEqual(eps.eps(), 0.0)

    def test_eps_counts_events_in_window(self) -> None:
        eps = EventsPerSecond(last_n_seconds=10)
        clock = [1000.0]
        with patch("frigate.util.builtin.time.monotonic", side_effect=lambda: clock[0]):
            eps.start()
            # one event per second for five seconds
            for _ in range(5):
                clock[0] += 1.0
                eps.update()
            # five events over the five seconds since start
            self.assertAlmostEqual(eps.eps(), 1.0)

    def test_old_timestamps_expire_from_window(self) -> None:
        eps = EventsPerSecond(last_n_seconds=10)
        clock = [0.0]
        with patch("frigate.util.builtin.time.monotonic", side_effect=lambda: clock[0]):
            eps.start()
            for _ in range(10):
                clock[0] += 1.0
                eps.update()
            # jump well past the window so every timestamp ages out
            clock[0] += 100.0
            self.assertEqual(eps.eps(), 0.0)


if __name__ == "__main__":
    unittest.main()
