"""Reproducible synthetic pipeline-versus-sequential rendering benchmark.

Run with PYTHONPATH=src python scripts/benchmark_pipeline.py. No user recordings
are accessed; all media is generated and removed inside a temporary directory.
"""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter

from config.pipeline import STAGE_ORDER
from config.settings import load_default
from processing.batch import run_batch
from processing.ffmpeg_runner import FFmpegRunner

BENCHMARK_STAGES = ("dehaze", "colour", "gamma", "contrast", "reduce")


def render(
    source: Path, operation: str, settings: dict, runner: FFmpegRunner
) -> tuple[Path, float]:
    """Time a verified batch render and reject an unsuccessful measurement.

    :param source: Source video for this render.
    :param operation: Registered standalone or pipeline operation.
    :param settings: Complete validated operation settings.
    :param runner: FFmpeg runner used for both benchmark variants.
    :return: Published output path and wall-clock seconds including probing.
    :raises RuntimeError: If rendering fails.
    """
    start = perf_counter()
    result = run_batch([source], operation, settings, runner, lambda *args: None)[0]
    elapsed = perf_counter() - start
    if result.status != "completed":
        raise RuntimeError(result.message)
    return result.output, elapsed


def benchmark(runner: FFmpegRunner, directory: Path, stabilise: bool = False) -> dict:
    """Measure a fixed five-stage pipeline and equivalent sequential operations.

    :param runner: Selected FFmpeg build.
    :param directory: Disposable directory for all generated media.
    :param stabilise: Whether to include motion analysis and correction.
    :return: Measurement summary with pass counts, encoded outputs, bytes and timings.
    """
    # Generate one repeatable input for both variants. Source creation happens
    # before render() starts timing, so it is excluded from both measurements.
    source = directory / "synthetic.mp4"
    subprocess.run(
        [
            runner.ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=30:duration=3",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )

    # Use active corrections so this measures real filter work rather than
    # neutral bypasses. Both variants use the same stage order and parameters.
    settings = load_default("enhance")
    stages = STAGE_ORDER if stabilise else BENCHMARK_STAGES
    settings["enabled"] = list(stages)
    settings["stages"]["colour"]["blue_gain"] = 0.75
    settings["stages"]["gamma"].update(gamma=1.2, shadow_lift=0.15)
    settings["stages"]["contrast"]["contrast"] = 1.1
    settings.update(preset="ultrafast", reduction_preset="ultrafast")

    # Record actual executions: VidStab analysis is an FFmpeg call but has no
    # video encoder, so invocation and encode counts must be tracked separately.
    calls = []
    run = runner.run

    def record(arguments: list[str], *args: object) -> None:
        """Count actual FFmpeg executions and video encoders.

        :param arguments: Executed FFmpeg arguments.
        :param args: Remaining runner parameters forwarded unchanged.
        """
        calls.append(arguments)
        run(arguments, *args)

    runner.run = record

    # Measure the combined plan first, retaining its counts before clearing the
    # recorder for the sequential run. Timings include probing and publication.
    pipeline_output, combined_time = render(source, "enhance", settings, runner)
    combined_calls = len(calls)
    combined_encodes = sum(arguments.count("-c:v") for arguments in calls)
    calls.clear()
    current = source
    sequential_time = 0.0
    intermediate_bytes = 0

    # Reproduce manual sequential processing by feeding each published output
    # into the next operation. This deliberately incurs repeated lossy encoding.
    for operation in stages:
        standalone = load_default(operation) | settings["stages"][operation]

        # Match the final reduction quality across variants; earlier standalone
        # outputs use the normal quality setting, as separate user runs would.
        standalone.update(
            crf=settings["reduction_crf"] if operation == "reduce" else settings["crf"],
            preset="ultrafast",
            output_name=f"sequential-{operation}.mp4",
        )
        current, elapsed = render(current, operation, standalone, runner)
        sequential_time += elapsed

        # Count only video files needed between stages, excluding the final
        # deliverable. The combined plan creates no such intermediate videos.
        if operation != "reduce":
            intermediate_bytes += current.stat().st_size

    # Report final sizes separately: repeated compression changes the pixels,
    # so matching encoder settings do not imply identical quality or file size.
    return {
        "source": "synthetic testsrc2, 640x360, 30 fps, 3 seconds, no audio",
        "stages": list(stages),
        "final_encoding": "libx264, CRF 26, ultrafast, yuv420p",
        "ffmpeg_version": runner.version.splitlines()[0],
        "combined": {
            "seconds": round(combined_time, 3),
            "render_calls": combined_calls,
            "video_encodes": combined_encodes,
            "intermediate_video_bytes": 0,
            "final_bytes": pipeline_output.stat().st_size,
        },
        "sequential": {
            "seconds": round(sequential_time, 3),
            "render_calls": len(calls),
            "video_encodes": sum(arguments.count("-c:v") for arguments in calls),
            "intermediate_video_bytes": intermediate_bytes,
            "final_bytes": current.stat().st_size,
        },
        "quality_note": (
            "Repeated lossy encoding changes pixels; timings do not establish quality equivalence."
        ),
    }


def main() -> None:
    """Print benchmark measurements without persisting generated test media."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", default="", help="Optional absolute FFmpeg executable")
    parser.add_argument("--ffprobe", default="", help="Optional absolute FFprobe executable")
    parser.add_argument("--stabilise", action="store_true", help="Include VidStab stabilisation")
    arguments = parser.parse_args()
    runner = FFmpegRunner(arguments.ffmpeg, arguments.ffprobe)
    with tempfile.TemporaryDirectory(prefix="reefframe-benchmark-") as directory:
        print(json.dumps(benchmark(runner, Path(directory), arguments.stabilise), indent=2))


if __name__ == "__main__":
    main()
