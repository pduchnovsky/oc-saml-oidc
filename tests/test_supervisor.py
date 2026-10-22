"""Tests for supervisor runtime preparation."""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from omada_saml_oidc import supervisor
from omada_saml_oidc.config import BridgeConfig
from omada_saml_oidc.supervisor import PreparedRuntime, prepare_runtime
from tests.test_config import valid_env


def test_existing_certificate_path_does_not_load_cryptography(tmp_path: Path) -> None:
    """Skip crypto imports when persisted certificate files already exist."""

    cert_path = tmp_path / "frontend.crt"
    key_path = tmp_path / "frontend.key"
    cert_path.touch()
    key_path.touch()
    script = """
import sys
from pathlib import Path
from omada_saml_oidc.certs import ensure_self_signed_certificate

ensure_self_signed_certificate(
    cert_path=Path(sys.argv[1]),
    key_path=Path(sys.argv[2]),
    common_name="bridge.example.com",
    subject_alt_names=("bridge.example.com", "localhost"),
)
print("cryptography" in sys.modules)
"""

    result = subprocess.run(
        [sys.executable, "-c", script, str(cert_path), str(key_path)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_prepare_runtime_writes_generated_runtime_files(tmp_path: Path) -> None:
    """Write persistent and runtime files required by bridge services."""

    config = BridgeConfig.from_env(valid_env(tmp_path))

    runtime = prepare_runtime(config)

    assert runtime.secret_path.exists()
    assert runtime.cert_path.exists()
    assert runtime.key_path.exists()
    assert runtime.bridge_config_path.exists()
    assert runtime.satosa_config_path.exists()


def test_prepare_runtime_persists_provided_state_secret(tmp_path: Path) -> None:
    """Persist a caller-provided SATOSA state encryption key on first run."""

    env = valid_env(tmp_path)
    env["SATOSA_STATE_ENCRYPTION_KEY"] = "provided-state-key"
    config = BridgeConfig.from_env(env)

    runtime = prepare_runtime(config)

    assert runtime.secret_path.read_text().strip() == "provided-state-key"


def test_run_supervisor_starts_satosa_in_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run the SATOSA server as one of the supervisor's service threads."""

    config = BridgeConfig.from_env(valid_env(tmp_path))
    runtime = PreparedRuntime(
        secret_path=tmp_path / "state-secret",
        cert_path=tmp_path / "frontend.crt",
        key_path=tmp_path / "frontend.key",
        bridge_config_path=tmp_path / "bridge.yaml",
        satosa_config_path=tmp_path / "satosa.yaml",
    )
    runtime.secret_path.write_text("state-secret")
    monkeypatch.setattr(supervisor, "prepare_runtime", lambda _: runtime)
    monkeypatch.setenv("OMADA_BRIDGE_CONFIG", "original-bridge-config")
    monkeypatch.setenv("SATOSA_CONFIG", "original-satosa-config")
    monkeypatch.setenv("SATOSA_STATE_ENCRYPTION_KEY", "original-state-secret")

    started_threads: list[FakeThread] = []
    handlers: dict[int, Callable[..., object]] = {}
    satosa_server_state: dict[str, object] = {}

    def create_satosa_server(
        port: int, threads: int
    ) -> tuple[Callable[[], None], Callable[[], None]]:
        """Capture SATOSA listener settings and its shutdown callback."""

        satosa_server_state["port"] = port
        satosa_server_state["threads"] = threads

        def run() -> None:
            """Stand in for the Waitress event loop."""

        satosa_server_state["runner"] = run

        def stop() -> None:
            """Record the listener shutdown request."""

            satosa_server_state["stopped"] = True

        return run, stop

    monkeypatch.setattr(supervisor, "create_satosa_server", create_satosa_server)

    class FakeThread:
        """Capture service thread configuration without starting servers."""

        def __init__(
            self,
            target: Callable[..., object],
            args: tuple[object, ...],
            name: str,
            daemon: bool,
        ) -> None:
            self.target = target
            self.args = args
            self.name = name
            self.daemon = daemon

        def start(self) -> None:
            """Record that the supervisor started this service."""

            started_threads.append(self)

        def is_alive(self) -> bool:
            """Keep captured services alive until the test requests shutdown."""

            return True

        def join(self, timeout: float | None = None) -> None:
            """Record that the supervisor waited for this service to stop."""

            satosa_server_state["join_timeout"] = timeout

    class FakeEvent:
        """Request shutdown on the first supervisor wait."""

        def __init__(self) -> None:
            self.set_called = False

        def is_set(self) -> bool:
            """Return whether shutdown has been requested."""

            return self.set_called

        def set(self) -> None:
            """Mark shutdown as requested."""

            self.set_called = True

        def wait(self, timeout: float | None = None) -> bool:
            """Invoke the registered signal handler to end the supervisor loop."""

            _ = timeout
            handlers[int(signal.SIGTERM)](int(signal.SIGTERM), None)
            return self.set_called

    def capture_signal(signum: int, handler: Callable[..., object]) -> None:
        """Capture installed signal handlers for the fake event."""

        handlers[signum] = handler

    monkeypatch.setattr(supervisor, "Thread", FakeThread)
    monkeypatch.setattr(supervisor, "Event", FakeEvent)
    monkeypatch.setattr(supervisor.signal, "signal", capture_signal)

    assert supervisor.run_supervisor(config) == 0

    satosa_thread = next(thread for thread in started_threads if thread.name == "satosa")
    satosa_runner = satosa_server_state.pop("runner")
    assert len(started_threads) == 4
    assert satosa_thread.target is satosa_runner
    assert satosa_thread.args == ()
    assert satosa_thread.daemon is True
    assert satosa_server_state == {
        "port": 18000,
        "threads": 1,
        "stopped": True,
        "join_timeout": 7,
    }
    assert os.environ["OMADA_BRIDGE_CONFIG"] == str(runtime.bridge_config_path)
    assert os.environ["SATOSA_CONFIG"] == str(runtime.satosa_config_path)
    assert os.environ["SATOSA_STATE_ENCRYPTION_KEY"] == "state-secret"
