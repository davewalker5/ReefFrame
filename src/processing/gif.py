"""Palette-based GIF rendering."""

from pathlib import Path

from config.settings import validate


def build_arguments(source: Path, destination: Path, settings: dict) -> list[str]:
    """
    Build a palette-generated GIF, with optional original-left comparison.

    :param source: Path to the source video, which must remain unchanged.
    :param destination: Path at which the generated output will be written or published.
    :param settings: Complete operation settings; validated before use.
    :return: Ordered FFmpeg arguments, excluding the executable and runner-wide options.
    :raises ValueError: If the operation settings are invalid.
    """
    s = validate("gif", settings)
    graph = f"[0:v:0]fps={s['fps']},scale={s['width']}:-1:flags=lanczos"
    if s["comparison"]:
        graph += ",split[left][right];[left][right]hstack=inputs=2"
    graph += (
        f",split[a][b];[a]palettegen=max_colors={s['colors']}[p];"
        f"[b][p]paletteuse=dither={s['dither']}[v]"
    )
    return [
        "-i",
        str(source),
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-an",
        "-loop",
        str(s["loop"]),
        str(destination),
    ]
