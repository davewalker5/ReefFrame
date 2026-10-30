"""Timestamp-based RGB PNG extraction."""

from pathlib import Path

from config.settings import validate


def build_arguments(source: Path, destination: Path, settings: dict) -> list[str]:
    """
    Extract the first video stream at an explicit timestamp.

    :param source: Path to the source video, which must remain unchanged.
    :param destination: Path at which the generated output will be written or published.
    :param settings: Complete operation settings; validated before use.
    :return: Ordered FFmpeg arguments, excluding the executable and runner-wide options.
    :raises ValueError: If the operation settings are invalid.
    """
    s = validate("snapshot", settings)
    args = ["-ss", s["timestamp"], "-i", str(source)]
    if s["comparison"]:
        args += ["-filter_complex", "[0:v:0]split[a][b];[a][b]hstack=inputs=2[v]", "-map", "[v]"]
    else:
        args += ["-map", "0:v:0"]
    return args + ["-frames:v", "1", "-update", "1", "-pix_fmt", "rgb24", str(destination)]
