"""Global gamma and smooth, luma-only shadow lifting."""

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
    values = validate("gamma", settings)
    filters = []
    if values["gamma"] != 1:
        filters.append(f"eq=gamma={values['gamma']}")
    if values["shadow_lift"]:
        # Work in limited-range 8-bit YUV; retain chroma and taper to zero
        # with a continuous first derivative at the shadow-range boundary.
        extent = 219 * values["shadow_range"]
        lift = values["shadow_lift"] * extent
        filters.append(
            "scale=in_range=auto:out_range=tv,format=yuv444p,"
            f"lutyuv=y='val+{lift}*pow(clip(1-(val-16)/{extent},0,1),2)'"
        )
    return filtered_video(source, destination, values, ",".join(filters) or "null")
