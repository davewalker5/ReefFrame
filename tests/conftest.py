"""Deterministic headless GUI setup and synthetic media fixtures."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(scope="session")
def application():
    """
    Create a shared offscreen Qt application.

    :yields: Shared QApplication, kept alive until all GUI tests finish.
    """
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    instance = QApplication.instance() or QApplication([])
    yield instance
    # Dispose windows while Qt is alive, before Python tears down signal callbacks.
    for widget in instance.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def clip(tmp_path, request):
    """
    Generate a short video with an optional AAC audio track.

    :param tmp_path: Isolated temporary directory supplied by pytest.
    :param request: Pytest request whose optional parameter selects whether the clip contains audio.
    :return: Path to a one-second synthetic MP4 clip.
    """
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")
    audio = getattr(request, "param", True)
    path = tmp_path / "reef '海 footage.mp4"
    args = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=size=160x120:rate=12:duration=1",
    ]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "aac"]
    subprocess.run(args + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path
