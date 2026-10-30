"""Private-directory two-pass VidStab and independent comparison rendering."""

from pathlib import Path

from config.settings import validate
from processing.commands import COMPARISON_SCALE, audio_arguments, video_arguments


def build_phases(source: Path, destination: Path, settings: dict) -> list[tuple[str, list[str]]]:
    """
    Build phases referencing motion.trf exclusively inside the private working directory.

    :param source: Path to the source video, which must remain unchanged.
    :param destination: Path at which the generated output will be written or published.
    :param settings: Complete operation settings; validated before use.
    :return: Ordered phase labels and argument lists using motion.trf in the private directory.
    :raises ValueError: If the operation settings are invalid.
    """
    s = validate("stabilise", settings)
    detect = f"vidstabdetect=shakiness={s['shakiness']}:accuracy={s['accuracy']}:result=motion.trf"
    transform = (
        f"vidstabtransform=input=motion.trf:smoothing={s['smoothing']}:optzoom={s['optzoom']}"
    )
    phases = [
        (
            "Motion detection",
            ["-i", str(source), "-map", "0:v:0", "-vf", detect, "-an", "-f", "null", "-"],
        )
    ]
    if s["comparison"]:
        phases.append(
            (
                "Stabilising",
                [
                    "-i",
                    str(source),
                    "-map",
                    "0:v:0",
                    "-vf",
                    transform,
                    "-an",
                    "-c:v",
                    "ffv1",
                    "stable.mkv",
                ],
            )
        )
        graph = (
            "[0:v:0]setpts=PTS-STARTPTS[a];[1:v:0]setpts=PTS-STARTPTS[b];"
            f"[a][b]hstack=inputs=2:shortest=1,{COMPARISON_SCALE}[v]"
        )
        args = ["-i", str(source), "-i", "stable.mkv", "-filter_complex", graph, "-map", "[v]"]
    else:
        args = ["-i", str(source), "-map", "0:v:0", "-vf", transform]
    phases.append(
        ("Rendering", args + video_arguments(s) + audio_arguments(s, True) + [str(destination)])
    )
    return phases
