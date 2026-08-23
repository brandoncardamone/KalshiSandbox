"""RSA-PSS request signing for the Kalshi trade API.

The signing scheme here is carried over unchanged from the existing working
implementation in ExpectedValue/expectedvalue.py:

    message = str(unix_millis) + HTTP_METHOD + path_without_query
    signature = base64(RSA-PSS-SHA256(message))

with the signature and its timestamp sent as request headers. Query strings are
stripped before signing -- Kalshi signs the path only.

The one structural change is that the private key is parsed once at construction
instead of re-read from disk on every request, since the ingest layer issues many
concurrent calls.
"""

from __future__ import annotations

import base64
import datetime
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# Host targeted by the existing implementation. The spec (S3.1) says to keep
# whatever the working auth code already uses rather than switching hosts.
BASE_URL = "https://external-api.kalshi.com"
API_PREFIX = "/trade-api/v2"


def load_private_key_from_file(file_path: str | Path) -> rsa.RSAPrivateKey:
    """Load an unencrypted PEM RSA private key from disk."""
    with open(file_path, "rb") as key_file:
        return serialization.load_pem_private_key(
            key_file.read(),
            password=None,
            backend=default_backend(),
        )


def sign_pss_text(private_key: rsa.RSAPrivateKey, text: str) -> str:
    """Sign `text` with RSA-PSS/SHA-256 and return the base64 signature."""
    message = text.encode("utf-8")
    try:
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")
    except InvalidSignature as e:
        raise ValueError("RSA sign PSS failed") from e


class KalshiSigner:
    """Produces the three auth headers Kalshi expects on every request."""

    def __init__(self, api_key_id: str, private_key_path: str | Path):
        if not api_key_id:
            raise ValueError("KALSHI_API_KEY_ID is empty")
        key_path = Path(private_key_path).expanduser()
        if not key_path.is_file():
            raise FileNotFoundError(f"private key not found at {key_path}")
        self.api_key_id = api_key_id
        self.private_key = load_private_key_from_file(key_path)

    @classmethod
    def from_env(cls) -> "KalshiSigner":
        """Build from KALSHI_API_KEY_ID / KALSHI_API_KEY_PATH.

        Call dotenv.load_dotenv() before this if the values live in a .env file.
        """
        key_id = os.getenv("KALSHI_API_KEY_ID")
        key_path = os.getenv("KALSHI_API_KEY_PATH")
        missing = [
            name
            for name, val in (
                ("KALSHI_API_KEY_ID", key_id),
                ("KALSHI_API_KEY_PATH", key_path),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"missing env var(s): {', '.join(missing)}. "
                "Copy .env.example to .env and fill it in."
            )
        return cls(key_id, key_path)

    def headers(self, method: str, path: str) -> dict[str, str]:
        """Auth headers for `method` on `path`.

        `path` must be the full request path including the /trade-api/v2 prefix,
        e.g. "/trade-api/v2/markets". A query string, if present, is stripped
        before signing but should still be sent on the wire.
        """
        timestamp_ms = str(int(datetime.datetime.now().timestamp() * 1000))
        path_without_query = path.split("?")[0]
        signature = sign_pss_text(
            self.private_key, timestamp_ms + method.upper() + path_without_query
        )
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        }
