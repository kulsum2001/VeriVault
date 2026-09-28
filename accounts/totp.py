"""Minimal RFC 6238 time-based one-time passwords using only the standard library."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


def generate_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _decode(secret):
    secret = secret.replace(" ", "").upper()
    secret += "=" * (-len(secret) % 8)
    return base64.b32decode(secret)


def hotp(secret, counter, digits=6):
    digest = hmac.new(_decode(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp(secret, for_time=None, step=30, digits=6):
    for_time = time.time() if for_time is None else for_time
    return hotp(secret, int(for_time // step), digits)


def verify(secret, code, for_time=None, window=1, step=30):
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    for_time = time.time() if for_time is None else for_time
    counter = int(for_time // step)
    return any(
        hmac.compare_digest(hotp(secret, counter + offset), code)
        for offset in range(-window, window + 1)
    )


def provisioning_uri(secret, account, issuer="VeriVault"):
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(account)}"
        f"?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


def pretty(secret):
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
