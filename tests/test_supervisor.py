"""Tests for supervisor runtime preparation."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from omada_saml_oidc.config import BridgeConfig
from omada_saml_oidc.supervisor import prepare_runtime
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
    """Write persistent and runtime files required by child processes."""

    config = BridgeConfig.from_env(valid_env(tmp_path))

    runtime = prepare_runtime(config)

    assert runtime.secret_path.exists()
    assert runtime.cert_path.exists()
    assert runtime.key_path.exists()
    assert runtime.bridge_config_path.exists()
    assert runtime.satosa_config_path.exists()
    assert runtime.satosa_command[1:3] == (
        "-m",
        "omada_saml_oidc.satosa_server",
    )
    assert runtime.satosa_command[runtime.satosa_command.index("--threads") + 1] == "1"


def test_prepare_runtime_persists_provided_state_secret(tmp_path: Path) -> None:
    """Persist a caller-provided SATOSA state encryption key on first run."""

    env = valid_env(tmp_path)
    env["SATOSA_STATE_ENCRYPTION_KEY"] = "provided-state-key"
    config = BridgeConfig.from_env(env)

    runtime = prepare_runtime(config)

    assert runtime.secret_path.read_text().strip() == "provided-state-key"
