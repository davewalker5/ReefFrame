"""Correction transfer functions, validation and preset directory behaviour."""

import importlib
import shutil
import subprocess
from pathlib import Path

import pytest

from config.settings import load_default, validate
from gui.main_window import DIALOGS
from processing.batch import run_batch
from processing.ffmpeg_runner import FFmpegRunner


@pytest.mark.parametrize("operation", ["gamma", "colour", "contrast"])
def test_neutral_filter(operation):
    """Neutral controls bypass all intentional correction filters.

    :param operation: Correction operation name.
    """
    module = importlib.import_module("processing." + operation)
    arguments = module.build_arguments(Path("in.mp4"), Path("out.mp4"), load_default(operation))
    assert arguments[arguments.index("-vf") + 1] == "null"
    assert arguments[arguments.index("-c:a") + 1] == "copy"


@pytest.mark.parametrize(
    "key,value",
    [
        ("gamma", 0),
        ("gamma", float("nan")),
        ("shadow_lift", -0.1),
        ("shadow_lift", 0.501),
        ("shadow_range", 0),
        ("red_gain", 2.1),
        ("blue_gain", float("inf")),
        ("green_gain", True),
    ],
)
def test_invalid_correction(key, value):
    """Reject unsafe ranges and non-finite or boolean numeric settings.

    :param key: Correction parameter to invalidate.
    :param value: Invalid parameter value.
    """
    operation = "colour" if key.endswith("gain") else "gamma"
    with pytest.raises(ValueError):
        validate(operation, load_default(operation) | {key: value})


def render_pixels(operation: str, changes: dict, pixels: bytes, pixel_format: str) -> bytes:
    """Apply a generated filter to a single raw test frame without encoding loss.

    :param operation: Correction operation name.
    :param changes: Non-neutral settings for this test.
    :param pixels: Raw 256 by 1 test frame.
    :param pixel_format: Raw input and output pixel format.
    :return: Corrected raw frame bytes.
    """
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg unavailable")
    module = importlib.import_module("processing." + operation)
    arguments = module.build_arguments(
        Path("in.mp4"), Path("out.mp4"), load_default(operation) | changes
    )
    filters = arguments[arguments.index("-vf") + 1]
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pixel_format",
            pixel_format,
            "-video_size",
            "256x1",
            "-color_range",
            "tv",
            "-i",
            "pipe:0",
            "-vf",
            filters,
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            pixel_format,
            "pipe:1",
        ],
        input=pixels,
        capture_output=True,
        check=True,
    )
    return result.stdout


def test_shadow_transfer():
    """Lift shadows monotonically, preserve highlights and leave chroma untouched."""
    pixels = bytes(range(256)) + bytes([110] * 256) + bytes([140] * 256)
    result = render_pixels("gamma", {"shadow_lift": 0.5, "shadow_range": 0.35}, pixels, "yuv444p")
    assert result[16] > 16
    assert result[40] > 40
    assert result[100:236] == pixels[100:236]
    assert list(result[16:236]) == sorted(result[16:236])
    assert max(b - a for a, b in zip(result[16:235], result[17:236])) <= 2
    assert result[256:] == pixels[256:]


def test_gamma_direction():
    """Increasing gamma lightens midtones; decreasing it darkens them."""
    pixels = bytes(range(256)) + bytes([128] * 512)
    lighter = render_pixels("gamma", {"gamma": 1.5}, pixels, "yuv444p")
    darker = render_pixels("gamma", {"gamma": 0.7}, pixels, "yuv444p")
    assert lighter[100] > 100 > darker[100]


def test_blue_gain():
    """Reducing blue leaves red and green unchanged in an RGB test frame."""
    pixels = bytes([40, 60, 180] * 256)
    result = render_pixels("colour", {"blue_gain": 0.5}, pixels, "rgb24")
    assert abs(result[0] - 40) <= 1
    assert abs(result[1] - 60) <= 1
    assert abs(result[2] - 90) <= 1


@pytest.mark.parametrize(
    "operation,changes",
    [
        ("gamma", {"gamma": 1.2, "shadow_lift": 0.2}),
        ("colour", {"blue_gain": 0.7, "red_gain": 1.1}),
        ("contrast", {"contrast": 1.3}),
    ],
)
def test_correction_batch(clip, operation, changes):
    """Render active corrections through batch publication and preserve audio.

    :param clip: Synthetic source video.
    :param operation: Correction operation name.
    :param changes: Active correction parameters.
    """
    runner = FFmpegRunner()
    settings = load_default(operation) | changes | {"preset": "ultrafast"}
    result = run_batch([clip], operation, settings, runner, lambda *args: None)[0]
    assert result.status == "completed", result.message
    assert result.output != clip
    assert runner.probe(result.output).audio


def test_shared_preset_directory(application, tmp_path, monkeypatch):
    """Share successful preset paths across dialogs and fresh settings instances.

    :param application: Shared Qt application.
    :param tmp_path: Isolated preferences and preset directory.
    :param monkeypatch: Attribute patch fixture.
    """
    from config import settings
    from gui.dialogs import base_operation_dialog as base

    monkeypatch.setattr(settings, "user_directory", lambda: tmp_path)
    monkeypatch.setattr(base, "user_directory", lambda: tmp_path)
    folder = tmp_path / "chosen"
    folder.mkdir()
    saved = folder / "gamma.json"
    starts = []
    monkeypatch.setattr(base.QFileDialog, "getSaveFileName", lambda *args: (str(saved), ""))
    dialog = DIALOGS["gamma"]()
    dialog.export_preset()
    assert settings.load_preset(saved, "gamma") == load_default("gamma")
    assert settings.preset_directory(tmp_path) == folder
    other = DIALOGS["colour"]()
    monkeypatch.setattr(
        base.QFileDialog, "getOpenFileName", lambda *args: (starts.append(args[2]) or "", "")
    )
    other.import_preset()
    assert starts == [str(folder)]
    assert settings.preset_directory(tmp_path) == folder
    saved.unlink()
    folder.rmdir()
    assert settings.preset_directory(tmp_path) == tmp_path
    dialog.close()
    other.close()


def test_preset_import_and_failed_selection(application, tmp_path, monkeypatch):
    """Successful imports persist directories; failed loads and cancelled saves do not.

    :param application: Shared Qt application.
    :param tmp_path: Isolated preferences and preset directory.
    :param monkeypatch: Attribute patch fixture.
    """
    from config import settings
    from gui.dialogs import base_operation_dialog as base

    monkeypatch.setattr(settings, "user_directory", lambda: tmp_path)
    monkeypatch.setattr(base, "user_directory", lambda: tmp_path)
    imported = tmp_path / "imported" / "colour.json"
    settings.save_preset(imported, "colour", load_default("colour") | {"blue_gain": 0.6})
    monkeypatch.setattr(base.QFileDialog, "getOpenFileName", lambda *args: (str(imported), ""))
    dialog = DIALOGS["colour"]()
    dialog.import_preset()
    assert dialog.settings()["blue_gain"] == 0.6
    assert settings.preset_directory(tmp_path) == imported.parent
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}")
    monkeypatch.setattr(base.QMessageBox, "warning", lambda *args: None)
    monkeypatch.setattr(base.QFileDialog, "getOpenFileName", lambda *args: (str(invalid), ""))
    dialog.import_preset()
    assert dialog.settings()["blue_gain"] == 0.6
    assert settings.preset_directory(tmp_path) == imported.parent
    monkeypatch.setattr(base.QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    dialog.export_preset()
    assert settings.preset_directory(tmp_path) == imported.parent
    dialog.close()


def test_contrast_transfer():
    """Standalone contrast expands tones about the midpoint without changing chroma."""
    pixels = bytes(range(256)) + bytes([128] * 512)
    result = render_pixels("contrast", {"contrast": 1.3}, pixels, "yuv444p")
    assert result[70] < 70
    assert result[180] > 180
    assert result[256:] == pixels[256:]


def test_contrast_filter_is_independent():
    """Contrast requests only EQ contrast, leaving the Enhance chain independent."""
    from processing.contrast import build_arguments

    arguments = build_arguments(
        Path("in.mp4"), Path("out.mp4"), load_default("contrast") | {"contrast": 1.3}
    )
    assert arguments[arguments.index("-vf") + 1] == "eq=contrast=1.3"
