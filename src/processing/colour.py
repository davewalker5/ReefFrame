"""Manual RGB channel gains without automatic tonal correction."""

from pathlib import Path

from config.settings import validate
from processing.commands import filtered_video


def build_arguments(source: Path, destination: Path, settings: dict) -> list[str]:
    """Build an independent correction render with shared media handling.

    :param source: Original video to preserve.
    :param destination: Output video path.
    :param settings: Complete validated correction settings.
    :return: FFmpeg arguments excluding executable and runner options.
    :raises ValueError: If settings are invalid.
    """
    values = validate("colour", settings)
    filters = "null"
    if any(values[key] != 1 for key in ("red_gain", "green_gain", "blue_gain")):
        filters = (
            f"colorchannelmixer=rr={values['red_gain']}:"
            f"gg={values['green_gain']}:bb={values['blue_gain']}"
        )
    return filtered_video(source, destination, values, filters)
