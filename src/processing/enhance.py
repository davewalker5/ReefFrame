"""Ordered enhancement planning with one final video encode and optional motion analysis."""

from dataclasses import dataclass
from pathlib import Path

from config.pipeline import PipelineConfiguration
from processing.commands import COMPARISON_SCALE, audio_arguments, filtered_video, video_arguments
from processing.correction_filters import (
    colour_filter,
    contrast_filter,
    dehaze_filter,
    gamma_filter,
    motion_detection_filter,
    stabilise_filter,
)

FILTER_BUILDERS = {
    "stabilise": stabilise_filter,
    "dehaze": dehaze_filter,
    "colour": colour_filter,
    "gamma": gamma_filter,
    "contrast": contrast_filter,
}


@dataclass(frozen=True)
class PipelinePlan:
    """An explicit processing plan with no encoded intermediate video."""

    phases: tuple[tuple[str, list[str]], ...]
    filters: tuple[str, ...]
    keep_motion: bool


def required_filters(configuration: PipelineConfiguration) -> tuple[str, ...]:
    """List only effective stage filters, including motion analysis when selected.

    :param configuration: Validated, ordered pipeline configuration.
    :return: Required FFmpeg filter capability names.
    """
    required = set()
    for stage in configuration.stages:
        parameters = stage.parameters
        if stage.operation == "stabilise":
            required.update(("vidstabdetect", "vidstabtransform"))
        elif stage.operation == "dehaze":
            required.add("eq")
        elif stage.operation == "contrast" and parameters["contrast"] != 1:
            required.add("eq")
        elif stage.operation == "colour" and colour_filter(parameters) != "null":
            required.add("colorchannelmixer")
        elif stage.operation == "gamma":
            if parameters["gamma"] != 1:
                required.add("eq")
            if parameters["shadow_lift"]:
                required.update(("scale", "format", "lutyuv"))
    if not required:
        required.add("null")
    if configuration.comparison:
        required.update(("split", "setpts", "hstack", "scale"))
    return tuple(sorted(required))


def render_arguments(
    source: Path, destination: Path, configuration: PipelineConfiguration, filters: str
) -> list[str]:
    """Build a single decode/split/render with one final encoder and audio mapping.

    :param source: Original source, decoded once in this render.
    :param destination: Temporary output video path.
    :param configuration: Validated pipeline settings.
    :param filters: Ordered effective correction filter chain.
    :return: Final render arguments without runner-wide options.
    """
    settings = configuration.output_settings()
    if not configuration.comparison:
        return filtered_video(source, destination, settings, filters)
    # Normalise the common timeline before splitting, including non-zero-start trials.
    graph = (
        f"[0:v:0]setpts=PTS-STARTPTS,split[left][work];[work]{filters}[right];"
        f"[left][right]hstack=inputs=2:shortest=1,{COMPARISON_SCALE}[v]"
    )
    return (
        ["-i", str(source), "-filter_complex", graph, "-map", "[v]"]
        + video_arguments(settings)
        + audio_arguments(settings)
        + [str(destination)]
    )


def build_plan(source: Path, destination: Path, settings: dict) -> PipelinePlan:
    """Plan motion analysis when needed, then one complete final render.

    :param source: Original source video, preserved throughout processing.
    :param destination: Temporary final output path.
    :param settings: Complete version-two pipeline settings.
    :return: Ordered phases and effective filters for execution and diagnostics.
    :raises ValueError: If pipeline configuration is invalid.
    """
    configuration = PipelineConfiguration.from_settings(settings)
    filters = tuple(
        FILTER_BUILDERS[stage.operation](stage.parameters)
        for stage in configuration.stages
        if stage.operation in FILTER_BUILDERS
    )
    chain = ",".join(expression for expression in filters if expression != "null") or "null"
    phases = []
    for stage in configuration.stages:
        if stage.operation == "stabilise":
            phases.append(
                (
                    "Motion detection",
                    [
                        "-i",
                        str(source),
                        "-map",
                        "0:v:0",
                        "-vf",
                        motion_detection_filter(stage.parameters),
                        "-an",
                        "-f",
                        "null",
                        "-",
                    ],
                )
            )
    phases.append(
        ("Rendering pipeline", render_arguments(source, destination, configuration, chain))
    )
    return PipelinePlan(tuple(phases), filters, configuration.keeps_motion())


def build_phases(source: Path, destination: Path, settings: dict) -> list[tuple[str, list[str]]]:
    """Expose the processing plan through the shared phase-execution interface.

    :param source: Original source video.
    :param destination: Temporary final output path.
    :param settings: Complete pipeline settings.
    :return: Motion analysis if needed and one final video-render phase.
    """
    return list(build_plan(source, destination, settings).phases)


def build_arguments(source: Path, destination: Path, settings: dict) -> list[str]:
    """Return the final render arguments; execution must use build_phases.

    :param source: Original source video.
    :param destination: Temporary final output path.
    :param settings: Complete pipeline settings.
    :return: Final render arguments, excluding optional motion analysis.
    """
    return build_plan(source, destination, settings).phases[-1][1]
