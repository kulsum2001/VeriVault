"""Generators for realistic-looking (but fictional) sample files - stdlib only."""
import struct
import zlib


def _pdf_escape(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(title, lines):
    """Build a small, valid single-page PDF."""
    content = ["BT", "/F2 20 Tf", "56 780 Td", f"({_pdf_escape(title)}) Tj", "/F1 11 Tf", "0 -30 Td", "14 TL"]
    for line in lines:
        content.append(f"({_pdf_escape(line)}) '")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1", "replace")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def make_png(width=240, height=150, color=(31, 122, 108), accent=(190, 150, 60)):
    """A plain PNG card with a coloured band - stands in for a scanned image."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            if y < 34:
                px = color
            elif 60 < y < 64 or 80 < y < 84 or 100 < y < 104:
                px = accent if x < 150 else (225, 228, 224)
            else:
                px = (244, 245, 241)
            rows += bytes(px)

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


def make_text(title, lines):
    return ("\n".join([title, "=" * len(title), "", *lines, "", "SAMPLE DOCUMENT - fictional data for VeriVault demo."]) + "\n").encode()


def make_csv(rows):
    return ("\n".join(",".join(str(c) for c in r) for r in rows) + "\n").encode()
