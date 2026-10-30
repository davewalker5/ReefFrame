"""Enhance command generation, independent of the GUI."""

from pathlib import Path

from config.settings import validate
from processing.commands import filtered_video


def build_arguments(source: Path, destination: Path, settings: dict) -> list[str]:
    """
    Validate settings and return a direct FFmpeg argument list.

    :param source: Path to the source video, which must remain unchanged.
    :param destination: Path at which the generated output will be written or published.
    :param settings: Complete operation settings; validated before use.
    :return: Ordered FFmpeg arguments, excluding the executable and runner-wide options.
    :raises ValueError: If the operation settings are invalid.
    """
    s = validate("enhance", settings)
    return filtered_video(
        source,
        destination,
        s,
        f"eq=contrast={s['contrast']}:brightness={s['brightness']},eq=contrast={s['second_contrast']},vibrance=intensity={s['vibrance']}",
        False,
    )
