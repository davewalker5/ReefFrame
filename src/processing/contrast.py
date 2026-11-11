"""Standalone contrast adjustment using the Enhance pipeline's EQ filter."""

from pathlib import Path

from config.settings import validate
from processing.commands import filtered_video


def build_arguments(source: Path, destination: Path, settings: dict) -> list[str]:
    """Build a contrast-only render using shared encoding and audio handling.

    :param source: Original video to preserve.
    :param destination: Output video path.
    :param settings: Complete contrast settings to validate.
    :return: FFmpeg arguments excluding executable and runner options.
    :raises ValueError: If settings are invalid.
    """
    values = validate("contrast", settings)
    filters = f"eq=contrast={values['contrast']}" if values["contrast"] != 1 else "null"
    return filtered_video(source, destination, values, filters)
