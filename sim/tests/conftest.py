"""Shared fixtures. The ``broker`` fixture starts mosquitto if present, else an in-process amqtt."""

from __future__ import annotations

import asyncio
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def wait_for_port(port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _start_mosquitto(tmp_path: Path, port: int) -> subprocess.Popen[bytes] | None:
    exe = shutil.which("mosquitto")
    if exe is None:
        return None
    conf = tmp_path / "mosquitto.conf"
    conf.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\n", encoding="utf-8")
    proc = subprocess.Popen(
        [exe, "-c", str(conf)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    if wait_for_port(port):
        return proc
    proc.kill()
    return None


class _AmqttBroker(threading.Thread):
    def __init__(self, port: int) -> None:
        super().__init__(daemon=True)
        self.port = port
        self.ready = threading.Event()
        self.error: BaseException | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def run(self) -> None:
        from amqtt.broker import Broker

        config = {
            "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{self.port}"}},
            "plugins": {
                "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}
            },
        }
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.broker = Broker(config, loop=self.loop)
            self.loop.run_until_complete(self.broker.start())
        except BaseException as exc:  # noqa: BLE001
            self.error = exc
            self.ready.set()
            return
        self.ready.set()
        self.loop.run_forever()

    def stop(self) -> None:
        if self.loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broker.shutdown(), self.loop).result(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)


@pytest.fixture
def broker(tmp_path: Path) -> Iterator[tuple[str, int]]:
    """Yield ``(host, port)`` of a running local broker, or skip the test."""
    port = free_port()
    proc = _start_mosquitto(tmp_path, port)
    if proc is not None:
        yield "127.0.0.1", port
        proc.terminate()
        proc.wait(timeout=5)
        return
    try:
        import amqtt  # noqa: F401
    except ImportError:
        pytest.skip("no MQTT broker: mosquitto not on PATH and amqtt not installed (BLOCKERS.md)")
    thread = _AmqttBroker(port)
    thread.start()
    thread.ready.wait(timeout=15)
    if thread.error is not None or not wait_for_port(port, 5):
        pytest.skip(f"no MQTT broker: amqtt failed to start ({thread.error!r}) (BLOCKERS.md)")
    yield "127.0.0.1", port
    thread.stop()
