"""Sequential batch execution and atomic publication of verified outputs."""

import importlib
import logging
import os
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from config.settings import validate
from processing.ffmpeg_runner import CancelledError, FFmpegRunner
from processing.file_naming import eligible, output_path


@dataclass(frozen=True)
class JobResult:
    """Per-file outcome suitable for both GUI and programmatic clients."""

    source: Path
    status: str
    message: str
    output: Path | None = None


def publish(temporary: Path, destination: Path, overwrite: bool) -> None:
    """
    Publish a same-filesystem output atomically; no-overwrite resists races.

    :param temporary: Verified temporary output on the destination filesystem.
    :param destination: Path at which the generated output will be written or published.
    :param overwrite: Whether an existing destination may be atomically replaced.
    :raises OSError: If publication fails, including an existing destination when overwrite is
        disabled.
    """
    if overwrite:
        os.replace(temporary, destination)
    else:
        os.link(temporary, destination)
        temporary.unlink()


def run_batch(
    sources: Iterable[Path],
    operation: str,
    settings: dict,
    runner: FFmpegRunner,
    event: Callable[[str, float, str], None],
    stop_on_error: bool = False,
) -> list[JobResult]:
    """
    Process a frozen queue sequentially, preserving source and existing outputs on failure.

    :param sources: Input paths captured before processing starts.
    :param operation: Registered operation name used to select defaults and processing behaviour.
    :param settings: Complete operation settings; validated before use.
    :param runner: FFmpeg runner providing capability checks, probing, execution and cancellation.
    :param event: Callback receiving filename, percentage and message; negative percentages identify
        logs or counts.
    :param stop_on_error: Whether to stop at the first failed file instead of continuing the queue.
    :return: Per-file outcomes for attempted or skipped files; cancellation leaves later files
        unstarted.
    :raises ValueError: If batch settings are invalid; per-file errors are returned as outcomes.
    """
    settings = validate(operation, settings)
    queue = tuple(Path(source).absolute() for source in sources)
    results = []
    destinations = set()
    source_paths = {str(path.resolve()).casefold() for path in queue}
    logging.getLogger(__name__).info("%s settings: %s", operation, settings)
    for source in queue:
        if runner.cancelled.is_set():
            break
        try:
            if not eligible(source, operation):
                results.append(JobResult(source, "skipped", "Ineligible input"))
                continue
            destination = output_path(source, operation, settings)
            key = str(destination.resolve()).casefold()
            if key in source_paths:
                raise ValueError("Output matches a queued source file")
            if key in destinations:
                results.append(
                    JobResult(source, "skipped", "Batch destination collision", destination)
                )
                continue
            destinations.add(key)
            if (destination.exists() or destination.is_symlink()) and not settings["overwrite"]:
                results.append(JobResult(source, "skipped", "Output already exists", destination))
                continue
            reason = runner.unavailable(operation, settings["comparison"])
            if reason:
                raise ValueError(reason)
            metadata = runner.probe(source)
            if operation == "snapshot":
                hours, minutes, seconds = settings["timestamp"].split(":")
                if (
                    metadata.duration
                    and int(hours) * 3600 + int(minutes) * 60 + float(seconds) >= metadata.duration
                ):
                    raise ValueError("Snapshot timestamp is beyond the video duration")
            motion_destination = destination.with_suffix(".trf")
            if (
                settings.get("keep_motion")
                and (motion_destination.exists() or motion_destination.is_symlink())
                and not settings["overwrite"]
            ):
                raise FileExistsError(f"Motion data already exists: {motion_destination}")
            with tempfile.TemporaryDirectory(prefix=".reefframe-", dir=source.parent) as directory:
                work = Path(directory)
                temporary = work / ("result" + destination.suffix)
                module = importlib.import_module("processing." + operation)
                phases = (
                    module.build_phases(source, temporary, settings)
                    if operation == "stabilise"
                    else [("Rendering", module.build_arguments(source, temporary, settings))]
                )
                for phase, arguments in phases:
                    event(source.name, 0, phase)
                    runner.run(
                        arguments,
                        work,
                        metadata.duration,
                        lambda percent: event(source.name, percent, phase),
                        lambda line: event(source.name, -1, line),
                    )
                if not temporary.is_file() or temporary.stat().st_size == 0:
                    raise ValueError("FFmpeg did not produce a nonempty output")
                runner.probe(temporary)
                if runner.cancelled.is_set():
                    raise CancelledError("Cancelled")
                if settings.get("keep_motion"):
                    publish(work / "motion.trf", motion_destination, settings["overwrite"])
                publish(temporary, destination, settings["overwrite"])
            results.append(JobResult(source, "completed", "Created output", destination))
            # Duration-based FFmpeg estimates can stop below 100 even on success.
            event(source.name, 100, "Completed")
        except CancelledError:
            results.append(JobResult(source, "cancelled", "Cancelled"))
            break
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            results.append(JobResult(source, "failed", str(error)))
            event(source.name, -1, str(error))
            if stop_on_error:
                break
        finally:
            counts = {
                status: sum(result.status == status for result in results)
                for status in ("completed", "skipped", "failed", "cancelled")
            }
            event(
                source.name, -2, " • ".join(f"{count} {status}" for status, count in counts.items())
            )
    return results
