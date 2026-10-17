"""Tests for the inter-process REP/REQ communicator."""

import os
import tempfile
import unittest
from unittest.mock import patch

import zmq

from frigate.comms import inter_process
from frigate.comms.inter_process import (
    InterProcessCommunicator,
    InterProcessRequestor,
)


class TestInterProcessCommunicator(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        address = f"ipc://{os.path.join(self.tmp.name, 'comms')}"
        self.patcher = patch.object(inter_process, "SOCKET_REP_REQ", address)
        self.patcher.start()

        self.communicator = InterProcessCommunicator()
        self.communicator.subscribe(self._dispatch)
        self.communicator.start()

        self.requestor = InterProcessRequestor()
        # fail the test instead of hanging forever if no reply is sent
        self.requestor.socket.setsockopt(zmq.RCVTIMEO, 5000)

    def tearDown(self) -> None:
        self.requestor.stop()
        self.communicator.stop()
        self.patcher.stop()
        self.tmp.cleanup()

    @staticmethod
    def _dispatch(topic: str, value):
        if topic == "boom":
            raise RuntimeError("dispatcher failure")

        return {"topic": topic, "value": value}

    def test_reply_is_returned(self) -> None:
        assert self.requestor.send_data("ok", 1) == {"topic": "ok", "value": 1}

    def test_dispatcher_exception_still_replies(self) -> None:
        with self.assertLogs("frigate.comms.inter_process", level="ERROR"):
            assert self.requestor.send_data("boom", None) == []

        # the reader thread and the REP socket must keep working afterwards
        assert self.communicator.reader_thread.is_alive()
        assert self.requestor.send_data("ok", 2) == {"topic": "ok", "value": 2}


if __name__ == "__main__":
    unittest.main()
