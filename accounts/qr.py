"""Generate a scannable QR code (as SVG) for the TOTP setup page.

Uses the ``qrcode`` package's SVG image factory, which needs no image
library (no Pillow) - it draws the QR as vector paths, so it stays crisp
at any size and works offline with no external service.
"""
import io
import re

import qrcode
import qrcode.image.svg

_SVG_OPEN_TAG = re.compile(r"(<svg[^>]*>)")


def make_qr_svg(data, box_size=8, border=3):
    """Return a standalone SVG string (as text) encoding ``data``.

    A white background rectangle is baked in so the code stays scannable
    regardless of the page's light/dark theme or where it's viewed.
    """
    image = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=box_size, border=border)
    buffer = io.BytesIO()
    image.save(buffer)
    svg = buffer.getvalue().decode("utf-8")
    return _SVG_OPEN_TAG.sub(r'\1<rect width="100%" height="100%" fill="#ffffff"/>', svg, count=1)
