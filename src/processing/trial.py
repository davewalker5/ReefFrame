"""Validated, per-run trial intervals, separate from reusable processing presets."""

import math
from dataclasses import dataclass

TRIAL_OPERATIONS = ("dehaze", "enhance", "stabilise")


@dataclass(frozen=True)
class TrialRange:
    """An interval in seconds on the original video's timeline."""

    start: float
    end: float

    def validate(self, duration: float) -> None:
        """Reject invalid intervals and unknown source durations.

        :param duration: Probed source duration in seconds.
        :raises ValueError: If the interval lies outside the video or is empty.
        """
        if not all(math.isfinite(value) for value in (self.start, self.end, duration)):
            raise ValueError("Trial times and video duration must be finite")
        if not 0 <= self.start < self.end <= duration:
            raise ValueError("Trial times must satisfy 0 ≤ start < end ≤ video duration")

    def apply(self, arguments: list[str], source: str) -> list[str]:
        """Limit every original-source input, leaving intermediate inputs untouched.

        :param arguments: Original FFmpeg arguments for one processing phase.
        :param source: Absolute original-source filename.
        :return: Arguments with accurate input seeking and a bounded input duration.
        """
        result = []
        for index, argument in enumerate(arguments):
            if argument == "-i" and arguments[index + 1] == source:
                result.extend(["-ss", str(self.start), "-t", str(self.end - self.start)])
            result.append(argument)
        return result

    def suffix(self) -> str:
        """Return a filename-safe marker identifying the trial interval.

        :return: Trial marker with start and end expressed in seconds.
        """
        return f"-trial-{self.start:.15g}s-to-{self.end:.15g}s"
