"""Immutable defaults and strictly validated, versioned user presets."""

import json
import math
import re
import shutil
import sys
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import QStandardPaths

OPERATIONS = ("convert", "dehaze", "enhance", "reduce", "gif", "snapshot", "stabilise")
RANGES = {
    "crf": (0, 51),
    "contrast": (0, 3),
    "second_contrast": (0, 3),
    "brightness": (-1, 1),
    "vibrance": (-2, 2),
    "fps": (1, 120),
    "width": (16, 7680),
    "colors": (4, 256),
    "loop": (-1, 65535),
    "shakiness": (1, 10),
    "accuracy": (1, 15),
    "smoothing": (0, 1000),
    "optzoom": (0, 2),
}
CHOICES = {
    "preset": (
        "ultrafast",
        "superfast",
        "veryfast",
        "faster",
        "fast",
        "medium",
        "slow",
        "slower",
        "veryslow",
    ),
    "codec": ("libx264",),
    "pixel_format": ("yuv420p",),
    "audio_codec": ("aac",),
    "audio_policy": ("copy", "aac", "remove"),
    "image_type": ("png",),
    "dither": ("sierra2_4a", "bayer", "floyd_steinberg", "none"),
}


def user_directory() -> Path:
    """
    Return the writable per-user configuration directory.

    :return: Platform-specific user configuration directory; it may not exist yet.
    """
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))


def log_directory() -> Path:
    """Return the platform's application-local data directory for logs.

    :return: Log directory; it may not exist yet.
    """
    return Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
    ) / "logs"


def migrate_user_settings() -> None:
    """Copy legacy preferences and presets when their new locations do not exist."""
    legacy = Path.home() / (
        "Library/Application Support" if sys.platform == "darwin" else ".config"
    ) / "ReefFrame"
    destination = user_directory()
    if legacy == destination:
        return
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("preferences.ini", "presets"):
        source = legacy / name
        target = destination / name
        if source.exists() and not target.exists():
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)


def load_default(operation: str) -> dict:
    """
    Load immutable shipped defaults for an operation.

    :param operation: Registered operation name used to select defaults and processing behaviour.
    :return: Fresh dictionary of shipped settings for the operation.
    :raises ValueError: If the operation name is not registered.
    """
    if operation not in OPERATIONS:
        raise ValueError("Unknown operation")
    return json.loads(files("config").joinpath("defaults", operation + ".json").read_text())[
        "settings"
    ]


def validate(operation: str, settings: dict) -> dict:
    """
    Validate a complete settings object and return a copy; raise ValueError on errors.

    :param operation: Registered operation name used to select defaults and processing behaviour.
    :param settings: Complete operation settings; validated before use.
    :return: Validated copy of the supplied settings, leaving the input unchanged.
    :raises ValueError: If keys, types, ranges, values or output filenames are invalid.
    """
    expected = load_default(operation)
    if not isinstance(settings, dict) or settings.keys() != expected.keys():
        raise ValueError("Settings must contain exactly the documented keys")
    for key, default in expected.items():
        value = settings[key]
        valid = type(value) is type(default)
        if type(default) is float:
            valid = type(value) in (int, float) and math.isfinite(value)
        if not valid:
            raise ValueError(f"Invalid type for {key}")
        if key in RANGES and not RANGES[key][0] <= value <= RANGES[key][1]:
            raise ValueError(f"{key} must be between {RANGES[key]}")
        if key in CHOICES and value not in CHOICES[key]:
            raise ValueError(f"Unsupported {key}: {value}")
    if "timestamp" in settings and not re.fullmatch(
        r"[0-9]{2}:[0-5][0-9]:[0-5][0-9](\.[0-9]+)?", settings["timestamp"]
    ):
        raise ValueError("Timestamp must be HH:MM:SS[.fraction]")
    if "audio_bitrate" in settings and not re.fullmatch(
        r"[1-9][0-9]{0,3}k", settings["audio_bitrate"]
    ):
        raise ValueError("Audio bitrate must be a positive kbit/s value, e.g. 192k")
    name = settings["output_name"]
    if name and (Path(name).name != name or name in (".", "..") or "\\" in name):
        raise ValueError("Output name must be a filename, without a directory")
    return dict(settings)


def load_preset(path: Path, operation: str) -> dict:
    """
    Read and validate a preset for the requested operation.

    :param path: JSON preset path selected for import or export.
    :param operation: Registered operation name used to select defaults and processing behaviour.
    :return: Complete validated settings belonging to the requested operation.
    :raises ValueError: If JSON, schema version, operation or settings are invalid.
    :raises OSError: If the preset cannot be read.
    """
    document = json.loads(path.read_text())
    if not isinstance(document, dict) or set(document) != {"version", "operation", "settings"}:
        raise ValueError("Invalid preset structure")
    if (
        type(document["version"]) is not int
        or document["version"] != 1
        or document["operation"] != operation
    ):
        raise ValueError("Preset version or operation mismatch")
    return validate(operation, document["settings"])


def save_preset(path: Path, operation: str, settings: dict) -> None:
    """
    Save a complete validated preset without changing bundled defaults.

    :param path: JSON preset path selected for import or export.
    :param operation: Registered operation name used to select defaults and processing behaviour.
    :param settings: Complete operation settings; validated before use.
    :raises ValueError: If the settings are invalid.
    :raises OSError: If the directory or preset cannot be written.
    """
    document = dict(version=1, operation=operation, settings=validate(operation, settings))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n")
