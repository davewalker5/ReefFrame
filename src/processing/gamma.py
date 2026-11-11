"""Global gamma and smooth, luma-only shadow lifting."""

from pathlib import Path

from config.settings import validate
from processing.commands import filtered_video
from processing.correction_filters import gamma_filter


def build_arguments(source: Path, destination: Path, settings: dict) -> list[str]:
    """Build an independent correction render with shared media handling.

    :param source: Original video to preserve.
    :param destination: Output video path.
    :param settings: Complete validated correction settings.
    :return: FFmpeg arguments excluding executable and runner options.
    :raises ValueError: If settings are invalid.
    """
    values = validate("gamma", settings)
    return filtered_video(source, destination, values, gamma_filter(values))
