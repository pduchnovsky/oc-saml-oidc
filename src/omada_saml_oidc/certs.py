"""Persistent certificate generation for the SATOSA frontend."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CertificateBundle:
    """Describe the certificate and key files used by SATOSA."""

    cert_path: Path
    key_path: Path


def ensure_self_signed_certificate(
    *,
    cert_path: Path,
    key_path: Path,
    common_name: str,
    subject_alt_names: Iterable[str],
    valid_days: int = 365,
) -> CertificateBundle:
    """Persist a self-signed certificate and private key if needed.

    Args:
        cert_path: Destination path for the PEM certificate.
        key_path: Destination path for the PEM private key.
        common_name: Common name placed on the certificate subject.
        subject_alt_names: DNS names written into the certificate SAN.
        valid_days: Number of days the generated certificate should stay valid.

    Returns:
        A ``CertificateBundle`` describing the persisted files.
    """

    if cert_path.exists() and key_path.exists():
        return CertificateBundle(cert_path=cert_path, key_path=key_path)

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, common_name)])
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=valid_days))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(name) for name in subject_alt_names]),
            critical=False,
        )
    )
    certificate = builder.sign(private_key, hashes.SHA256())

    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_bytes = certificate.public_bytes(serialization.Encoding.PEM)

    key_path.write_bytes(key_bytes)
    cert_path.write_bytes(cert_bytes)
    with suppress(OSError):
        key_path.chmod(0o600)

    return CertificateBundle(cert_path=cert_path, key_path=key_path)
