"""Facilitates communication between processes."""

import logging
import multiprocessing as mp
import threading
from collections.abc import Callable
from multiprocessing.synchronize import Event as MpEvent
from typing import Any

import zmq

from frigate.comms.base_communicator import Communicator

logger = logging.getLogger(__name__)

SOCKET_REP_REQ = "ipc:///tmp/cache/comms"


class InterProcessCommunicator(Communicator):
    def __init__(self) -> None:
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(SOCKET_REP_REQ)
        self.stop_event: MpEvent = mp.Event()

    def publish(self, topic: str, payload: Any, retain: bool = False) -> None:
        """There is no communication back to the processes."""
        pass

    def subscribe(self, receiver: Callable) -> None:
        self._dispatcher = receiver
        self.reader_thread = threading.Thread(target=self.read)
        self.reader_thread.start()

    def read(self) -> None:
        while not self.stop_event.is_set():
            while True:  # load all messages that are queued
                has_message, _, _ = zmq.select([self.socket], [], [], 1)

                if not has_message:
                    break

                try:
                    raw = self.socket.recv_json(flags=zmq.NOBLOCK)
                except zmq.ZMQError:
                    break

                # A REP socket must send exactly one reply for every request it
                # receives. If the dispatcher raises, we still have to reply or
                # the waiting REQ side blocks forever in recv_json, deadlocking
                # every producer that shares this socket.
                try:
                    if isinstance(raw, list):
                        (topic, value) = raw
                        response = self._dispatcher(topic, value)
                    else:
                        logging.warning(
                            f"Received unexpected data type in ZMQ recv_json: {type(raw)}"
                        )
                        response = None
                except Exception:
                    logger.exception("Error handling inter-process request")
                    response = None

                try:
                    self.socket.send_json(response if response is not None else [])
                except zmq.ZMQError:
                    break

    def stop(self) -> None:
        self.stop_event.set()
        self.reader_thread.join()
        self.socket.close(linger=0)
        self.context.destroy(linger=0)


class InterProcessRequestor:
    """Simplifies sending data to InterProcessCommunicator and getting a reply."""

    def __init__(self) -> None:
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(SOCKET_REP_REQ)

    def send_data(self, topic: str, data: Any) -> Any:
        """Sends data and then waits for reply."""
        try:
            self.socket.send_json((topic, data))
            return self.socket.recv_json()
        except zmq.ZMQError:
            return ""

    def stop(self) -> None:
        self.socket.close(linger=0)
        self.context.destroy(linger=0)
