"""TOTP (RFC 6238) compatible with Google Authenticator, Microsoft Authenticator and 1Password:
SHA-1, 6 digits, 30-second steps, ±1 step tolerance, replay protection by step."""

import hmac
from datetime import UTC, datetime

import pyotp
import segno

DIGITS = 6
INTERVAL = 30
VALID_WINDOW = 1


def new_secret() -> str:
    return pyotp.random_base32(length=32)  # 160 bits, RFC 4226 recommendation


def provisioning_uri(secret: str, *, account: str, issuer: str) -> str:
    return pyotp.TOTP(secret, digits=DIGITS, interval=INTERVAL).provisioning_uri(
        name=account, issuer_name=issuer
    )


def qr_svg_data_uri(uri: str) -> str:
    return str(segno.make(uri, error="m").svg_data_uri(scale=4, border=2))


def verify(
    secret: str, code: str, *, last_used_step: int | None, at: datetime | None = None
) -> int | None:
    """Returns the matched time step, or None. A step equal to or older than
    `last_used_step` is rejected so a code cannot be replayed."""
    code = "".join(code.split())
    if len(code) != DIGITS or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret, digits=DIGITS, interval=INTERVAL)
    current = totp.timecode(at or datetime.now(UTC))
    for step in range(current - VALID_WINDOW, current + VALID_WINDOW + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(totp.generate_otp(step), code):
            return step
    return None
