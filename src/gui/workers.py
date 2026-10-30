"""Thread boundary for sequential processing."""

from PySide6.QtCore import QThread, Signal

from processing.batch import run_batch


class BatchWorker(QThread):
    """Emit progress and structured outcomes while keeping widgets on the GUI thread."""

    progress = Signal(str, float, str)
    outcomes = Signal(object)

    def __init__(self, sources: list, operation: str, settings: dict, runner: object) -> None:
        """
        Capture an immutable input queue and dedicated runner.

        :param sources: Input paths captured before processing starts.
        :param operation: Registered operation name used to select defaults and processing
            behaviour.
        :param settings: Complete operation settings; validated before use.
        :param runner: FFmpeg runner providing capability checks, probing, execution and
            cancellation.
        """
        super().__init__()
        self.sources = tuple(sources)
        self.operation = operation
        self.settings = dict(settings)
        self.runner = runner

    def run(self) -> None:
        """Run the core engine and deliver its per-file results."""
        results = run_batch(
            self.sources, self.operation, self.settings, self.runner, self.progress.emit
        )
        self.outcomes.emit(results)
