"""Direct FFmpeg execution with bounded cancellation and streaming diagnostics."""

import json
import logging
import os
import queue
import shlex
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class MediaInfo:
    """Probed duration and stream properties."""

    duration: float
    width: int
    height: int
    audio: bool


class CancelledError(RuntimeError):
    """The user cancelled the active job."""


def locate_tool(name: str, configured: str = "") -> str:
    """
    Locate an explicit executable, PATH tool, or common Homebrew installation.

    :param name: Executable name to locate.
    :param configured: Explicit executable path, or an empty string to search supported locations.
    :return: Absolute path to an executable matching the discovery policy.
    :raises FileNotFoundError: If no usable executable can be located.
    """
    # An invalid explicit path is an error; silently using another build could change capabilities.
    candidates = (
        [configured]
        if configured
        else [shutil.which(name)]
        + [
            f"{prefix}/{location}/{name}"
            for prefix in ("/opt/homebrew", "/usr/local")
            for location in ("opt/ffmpeg-full/bin", "bin")
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).absolute())
    raise FileNotFoundError(f"Cannot find {name}. Install FFmpeg or configure its absolute path.")


class FFmpegRunner:
    """Own dependency discovery, subprocess execution, and a cancellation event."""

    def __init__(self, ffmpeg: str = "", ffprobe: str = "") -> None:
        """
        Resolve executables; configured paths take precedence over PATH.

        :param ffmpeg: Explicit FFmpeg executable path, or an empty string for discovery.
        :param ffprobe: Explicit FFprobe executable path, or an empty string for discovery.
        :raises FileNotFoundError: If either executable cannot be located.
        :raises subprocess.CalledProcessError: If dependency inspection fails.
        """
        self.ffmpeg = locate_tool("ffmpeg", ffmpeg)
        self.ffprobe = locate_tool("ffprobe", ffprobe)
        self.cancelled = threading.Event()

        # Inspect the chosen binary rather than trusting its package or Homebrew formula name.
        self.filters = self._inspect("-filters")
        self.encoders = self._inspect("-encoders")
        self.version = self._inspect("-version")
        self.probe_version = subprocess.check_output([self.ffprobe, "-version"], text=True)
        LOGGER.info(
            "FFmpeg: %s\n%s\nFFprobe: %s\n%s",
            self.ffmpeg,
            self.version,
            self.ffprobe,
            self.probe_version,
        )

    def _inspect(self, option: str) -> str:
        """
        Return FFmpeg build information for a diagnostic option.

        :param option: FFmpeg information option such as -filters or -version.
        :return: Combined textual output from the requested FFmpeg information command.
        """
        return subprocess.check_output(
            [self.ffmpeg, "-hide_banner", option], text=True, stderr=subprocess.STDOUT
        )

    def unavailable(self, operation: str, comparison: bool = False) -> str:
        """
        Explain missing capabilities, or return an empty string.

        :param operation: Registered operation name used to select defaults and processing
            behaviour.
        :param comparison: Whether to include original-left, processed-right comparison behaviour.
        :return: Actionable missing-capability explanation, or an empty string when supported.
        """
        required = {
            "dehaze": ["eq"],
            "enhance": ["eq", "vibrance"],
            "gif": ["fps", "scale", "palettegen", "paletteuse"],
            "stabilise": ["vidstabdetect", "vidstabtransform"],
        }.get(operation, [])

        # Comparison needs composition filters; VidStab also uses a lossless intermediate.
        if comparison:
            required = [*required, "hstack", "split", "scale"]

        # Match complete capability names, not substrings of similarly named filters.
        missing = [name for name in required if name not in self.filters.split()]
        encoders = (
            ["png"] if operation == "snapshot" else ["gif"] if operation == "gif" else ["libx264"]
        )

        if operation in ("convert", "stabilise"):
            encoders.append("aac")

        if operation == "stabilise" and comparison:
            encoders.append("ffv1")

        missing += [name for name in encoders if name not in self.encoders.split()]
        return "Missing FFmpeg capabilities: " + ", ".join(missing) if missing else ""

    def probe(self, path: Path) -> MediaInfo:
        """
        Probe the first video stream; raise ValueError for invalid media.

        :param path: Filesystem path to inspect or read.
        :return: Duration in seconds, first-video dimensions in pixels, and audio presence.
        :raises ValueError: If metadata is invalid or there is no video stream.
        :raises subprocess.SubprocessError: If FFprobe fails or exceeds its timeout.
        """
        result = subprocess.run(
            [
                self.ffprobe,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        document = json.loads(result.stdout)

        # Processing maps 0:v:0, so metadata must describe that same first video stream.
        video = next((s for s in document["streams"] if s["codec_type"] == "video"), None)
        if video is None:
            raise ValueError("No video stream found")

        # Unknown duration is represented by zero and disables percentage estimation.
        return MediaInfo(
            float(document.get("format", {}).get("duration", 0)),
            int(video["width"]),
            int(video["height"]),
            any(s["codec_type"] == "audio" for s in document["streams"]),
        )

    def cancel(self) -> None:
        """Request termination and prevent subsequent phases from starting."""
        # A thread-safe event also prevents later batch phases from starting after cancellation.
        self.cancelled.set()

    def run(
        self,
        arguments: list[str],
        directory: Path,
        duration: float,
        progress: Callable[[float], None],
        log: Callable[[str], None],
    ) -> None:
        """
        Run an argument list, draining both pipes and terminating promptly on cancellation.

        :param arguments: FFmpeg arguments supplied separately, without shell interpretation.
        :param directory: Private working directory used by the child process.
        :param duration: Source duration in seconds; zero disables percentage estimation.
        :param progress: Callback receiving estimated progress percentages from zero to 100.
        :param log: Callback receiving command and diagnostic text for display.
        :raises CancelledError: If cancellation is requested before or during execution.
        :raises RuntimeError: If FFmpeg exits unsuccessfully.
        :raises OSError: If the child process cannot be started.
        """
        if self.cancelled.is_set():
            raise CancelledError("Cancelled")

        # Inputs are argument-list entries; shell quoting is used only for readable logging.
        # Noninteractive execution and no-overwrite protect private outputs from accidental reuse.
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-n",
            "-progress",
            "pipe:1",
            "-nostats",
            *arguments,
        ]
        LOGGER.info("%s", shlex.join(command))
        log(shlex.join(command))
        events = queue.Queue()
        with subprocess.Popen(
            command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        ) as process:

            def drain(stream: object, diagnostic: bool) -> None:
                """
                Drain one pipe on a separate thread to avoid deadlocks.

                :param stream: Readable subprocess text pipe to drain.
                :param diagnostic: Whether pipe lines are stderr diagnostics rather than progress
                    records.
                """
                for line in stream:
                    events.put((diagnostic, line.rstrip()))

            # Drain stdout and stderr independently: either full pipe could otherwise block FFmpeg.
            # Queue delivery keeps callbacks on the controlling worker thread, not reader threads.
            readers = [
                threading.Thread(target=drain, args=(stream, diagnostic), daemon=True)
                for stream, diagnostic in ((process.stdout, False), (process.stderr, True))
            ]
            for reader in readers:
                reader.start()
            errors = []

            # Process exit can precede pipe EOF; retain diagnostics still buffered by the readers.
            while (
                process.poll() is None
                or any(reader.is_alive() for reader in readers)
                or not events.empty()
            ):
                if self.cancelled.is_set() and process.poll() is None:
                    # Try graceful termination, then kill an encoder that does not stop.
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()

                try:
                    # A short timeout lets cancellation proceed even when FFmpeg produces no output.
                    diagnostic, line = events.get(timeout=0.1)
                except queue.Empty:
                    continue

                if diagnostic:
                    errors.append(line)

                    # Retain only a useful error tail; the complete diagnostic stream is logged.
                    errors = errors[-40:]
                    log(line)
                    LOGGER.info("%s", line)
                elif line.startswith("out_time_us=") and duration > 0:
                    value = line.partition("=")[2]
                    if value.lstrip("-").isdigit():
                        # Convert microseconds to percent, clamping negative preroll and overruns.
                        progress(min(100, max(0, int(value) / 10000 / duration)))

            for reader in readers:
                reader.join()

            # Cancellation is its own outcome even when termination produces a nonzero exit code.
            if self.cancelled.is_set():
                raise CancelledError("Cancelled")

            if process.wait() != 0:
                raise RuntimeError("FFmpeg failed: " + "\n".join(errors))
