"""Manual RGB channel gains without automatic tonal correction."""

from pathlib import Path

from config.settings import validate
from processing.commands import filtered_video
from processing.correction_filters import colour_filter


def build_arguments(source: Path, destination: Path, settings: dict) -> list[str]:
    """Build an independent correction render with shared media handling.

    :param source: Original video to preserve.
    :param destination: Output video path.
    :param settings: Complete validated correction settings.
    :return: FFmpeg arguments excluding executable and runner options.
    :raises ValueError: If settings are invalid.
    """
    values = validate("colour", settings)
    return filtered_video(source, destination, values, colour_filter(values))
