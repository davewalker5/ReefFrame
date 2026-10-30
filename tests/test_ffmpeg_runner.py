"""Execution cancellation and malformed probe handling."""

import threading

import pytest

from processing.ffmpeg_runner import CancelledError, FFmpegRunner, locate_tool


def test_bad_tool():
    """An explicit unavailable path never silently falls back."""
    with pytest.raises(FileNotFoundError):
        locate_tool("ffmpeg", "/missing/tool")


def test_cancel_running(tmp_path):
    """
    Cancellation terminates a live process even when waiting for output.

    :param tmp_path: Isolated temporary directory supplied by pytest.
    """
    runner = FFmpegRunner()
    timer = threading.Timer(0.3, runner.cancel)
    timer.start()
    try:
        with pytest.raises(CancelledError):
            runner.run(
                ["-re", "-f", "lavfi", "-i", "testsrc2=duration=30:size=64x64", "-f", "null", "-"],
                tmp_path,
                30,
                lambda value: None,
                lambda line: None,
            )
    finally:
        timer.cancel()
