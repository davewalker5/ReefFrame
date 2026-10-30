"""Regenerate original vector artwork as PNG, ICNS, and packaged window resource."""

import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main() -> None:
    """Render standard macOS icon sizes reproducibly from the SVG master."""
    application = QGuiApplication([])
    root = Path(__file__).resolve().parents[1]
    icons = root / "assets/icons"
    renderer = QSvgRenderer(str(icons / "reefframe.svg"))
    chunks = []
    for size, tag in (
        (16, b"icp4"),
        (32, b"icp5"),
        (64, b"icp6"),
        (128, b"ic07"),
        (256, b"ic08"),
        (512, b"ic09"),
        (1024, b"ic10"),
    ):
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, "PNG")
        payload = bytes(data)
        chunks.append(tag + struct.pack(">I", len(payload) + 8) + payload)
        if size == 1024:
            (icons / "reefframe.png").write_bytes(payload)
            (root / "src/resources/reefframe.png").write_bytes(payload)
    body = b"".join(chunks)
    (icons / "reefframe.icns").write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
    application.quit()


if __name__ == "__main__":
    main()
