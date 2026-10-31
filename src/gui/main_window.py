"""Folder browser, batch launch, and processing feedback."""

import importlib
import subprocess
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config.settings import OPERATIONS, user_directory
from gui.workers import BatchWorker
from processing.ffmpeg_runner import FFmpegRunner
from processing.file_naming import eligible, scan
from processing.trial import TRIAL_OPERATIONS

DIALOGS = {
    name: getattr(importlib.import_module(f"gui.dialogs.{name}_dialog"), name.title() + "Dialog")
    for name in OPERATIONS
}


class MainWindow(QMainWindow):
    """Present a focused file-based processing workflow."""

    def __init__(self) -> None:
        """Restore window preferences and initialise dependency diagnostics."""
        super().__init__()
        self.setWindowTitle("ReefFrame • Underwater video preparation")
        self.resize(1100, 760)

        # Keep window preferences separate from operation presets and installed resources.
        self.preferences = QSettings(
            str(user_directory() / "preferences.ini"), QSettings.Format.IniFormat
        )
        self.folder = Path(self.preferences.value("folder", str(Path.home())))
        self.worker = None
        self.close_requested = False
        self.runner = None
        self.paths = []
        self.setCentralWidget(QWidget())
        layout = QVBoxLayout(self.centralWidget())
        heading = QGridLayout()
        heading.setHorizontalSpacing(12)
        heading.setVerticalSpacing(2)
        icon = QLabel()
        icon.setAccessibleName("ReefFrame application icon")
        icon_size = 64
        pixel_ratio = self.devicePixelRatioF()

        # Scale raw image pixels explicitly: QIcon.pixmap may already apply the
        # display scale, which would double the size when multiplied again here.
        artwork = QPixmap(str(files("resources").joinpath("reefframe.png")))
        physical_size = round(icon_size * pixel_ratio)
        pixmap = artwork.scaled(
            physical_size,
            physical_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        pixmap.setDevicePixelRatio(pixel_ratio)
        icon.setPixmap(pixmap)
        icon.setFixedSize(icon_size, icon_size)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.addWidget(icon, 0, 0, 2, 1)
        title = QLabel("ReefFrame")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #25c6bb")
        heading.addWidget(title, 0, 1)
        heading.addWidget(QLabel("Prepare, enhance and refine your underwater footage"), 1, 1)
        heading.setColumnStretch(1, 1)
        layout.addLayout(heading)
        folder_row = QHBoxLayout()
        self.folder_label = QLabel(str(self.folder))
        self.folder_label.setStyleSheet(
            "background-color: #123f49; color: #e5faf7; border: 1px solid #277079; "
            "border-radius: 6px; padding: 8px 12px;"
        )
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        folder_row.addWidget(self.folder_label, 1)
        self.folder_button = QPushButton("Choose folder…")
        self.folder_button.clicked.connect(self.choose_folder)
        folder_row.addWidget(self.folder_button)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        folder_row.addWidget(refresh)
        layout.addLayout(folder_row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Filename", "Extension", "Size (MiB)", "Eligibility"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self.open_video)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 430)
        self.table.setStyleSheet(
            "QTableWidget::item:selected { background-color: #126d78; color: #ffffff; }"
        )
        layout.addWidget(self.table, 1)
        controls = QHBoxLayout()
        self.operation = QComboBox()
        self.operation.setStyleSheet(
            "QComboBox { background-color: #123f49; color: #e5faf7; "
            "border: 1px solid #277079; border-radius: 4px; padding: 5px 10px; }"
        )
        self.operation.addItems(OPERATIONS)
        self.operation.currentTextChanged.connect(self.refresh)
        controls.addWidget(QLabel("Operation"))
        controls.addWidget(self.operation)
        for label, callback in (
            ("Select all", self.table.selectAll),
            ("Deselect all", self.table.clearSelection),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
        self.selected_button = QPushButton("Process selected…")
        self.selected_button.clicked.connect(lambda: self.start_batch(False))
        controls.addWidget(self.selected_button)
        self.all_button = QPushButton("Process all eligible…")
        self.all_button.clicked.connect(lambda: self.start_batch(True))
        controls.addWidget(self.all_button)
        layout.addLayout(controls)
        self.status = QLabel("Ready")
        self.status.setStyleSheet(
            "background-color: #183348; color: #e9f4ff; border: 1px solid #42637e; "
            "border-radius: 6px; padding: 8px 12px;"
        )
        layout.addWidget(self.status)
        self.counts = QLabel("0 completed • 0 skipped • 0 failed • 0 cancelled")
        self.counts.setStyleSheet(
            "background-color: #303744; color: #f3f5fa; border: 1px solid #5c6575; "
            "border-radius: 6px; padding: 8px 12px;"
        )
        layout.addWidget(self.counts)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)

        # Bound the visible log so lengthy encodes do not grow the widget indefinitely.
        self.log.setMaximumBlockCount(3000)
        layout.addWidget(self.log)
        bottom = QHBoxLayout()
        diagnostics = QPushButton("Diagnostics / tool paths…")
        diagnostics.clicked.connect(self.diagnostics)
        bottom.addWidget(diagnostics)
        self.cancel_button = QPushButton("Cancel processing")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        bottom.addWidget(self.cancel_button)
        layout.addLayout(bottom)

        # Populate files and capability-dependent actions before restoring saved geometry.
        self.check_dependencies()
        self.refresh()
        geometry = self.preferences.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def check_dependencies(self) -> None:
        """Discover tools without making missing dependencies fatal to browsing."""
        try:
            self.runner = FFmpegRunner(
                str(self.preferences.value("ffmpeg", "")),
                str(self.preferences.value("ffprobe", "")),
            )
            self.log.appendPlainText(self.runner.ffmpeg + "\n" + self.runner.version)

        # Missing tools must leave folder browsing and diagnostics available.
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            self.runner = None
            self.log.appendPlainText(str(error))

    def choose_folder(self) -> None:
        """Choose an immediate folder with a native folder picker."""
        name = QFileDialog.getExistingDirectory(self, "Choose footage folder", str(self.folder))
        if name:
            self.folder = Path(name)
            self.preferences.setValue("folder", name)
            self.refresh()

    def refresh(self) -> None:
        """Refresh files and eligibility while preserving selected paths."""
        # Capture identities before rescanning: files can move to different sorted rows.
        selected = set(self.selected_paths())
        self.folder_label.setText(str(self.folder))
        try:
            self.paths = scan(self.folder)
        except OSError as error:
            self.log.appendPlainText(str(error))
            self.paths = []

        # Sorting during cell insertion can move a partly built row under the next cell.
        self.table.setSortingEnabled(False)

        # Qt keeps selection by row index when items are replaced. Clear it first,
        # then restore by file identity after rebuilding and sorting the table.
        self.table.clearSelection()
        self.table.clearContents()
        self.table.setRowCount(len(self.paths))
        operation = self.operation.currentText()
        for row, path in enumerate(self.paths):
            try:
                size = f"{path.stat().st_size / 1024**2:.2f}"
            # A file can disappear or become unreadable between the scan and its stat call.
            except OSError:
                size = "Unreadable"
            values = [
                path.name,
                path.suffix,
                size,
                "Eligible" if eligible(path, operation) else "Skipped",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)

                # Display text is presentation only; item data retains the actual source path.
                item.setData(Qt.ItemDataRole.UserRole, str(path))
                self.table.setItem(row, column, item)

        self.table.setSortingEnabled(True)
        for row in range(self.table.rowCount()):
            path = Path(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
            if path in selected:
                for column in range(self.table.columnCount()):
                    self.table.item(row, column).setSelected(True)
        reason = (
            self.runner.unavailable(operation)
            if self.runner
            else "FFmpeg / FFprobe unavailable; see Diagnostics"
        )

        # Both launch actions share the same capability and single-worker restrictions.
        busy = self.worker is not None
        for button in (self.selected_button, self.all_button):
            button.setEnabled(not busy and not reason)
            button.setToolTip(reason)

        # Refreshes during processing must not replace the active file/phase message.
        if not busy:
            self.status.setText(
                reason or f"{sum(eligible(p, operation) for p in self.paths)} eligible files"
            )

    def open_video(self, item: QTableWidgetItem) -> None:
        """Open the double-clicked video in the operating system's default player.

        :param item: Clicked table cell containing the video's stored filesystem path.
        """
        path = Path(item.data(Qt.ItemDataRole.UserRole)).absolute()
        if not path.is_file():
            QMessageBox.warning(self, "Cannot open video", f"Video no longer exists: {path}")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            QMessageBox.warning(
                self, "Cannot open video", f"Could not open the default player for: {path}"
            )

    def selected_paths(self) -> list[Path]:
        """
        Read selected sources using item data so sorting cannot change their identities.

        :return: Selected source paths identified by item data rather than visual row order.
        """
        return [
            Path(self.table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole))
            for index in self.table.selectionModel().selectedRows()
        ]

    def start_batch(self, all_eligible: bool) -> None:
        """
        Start processing selected or all eligible sources after accepting settings.

        :param all_eligible: Whether to use all eligible folder files instead of the selected rows.
        """
        if self.worker is not None or self.runner is None:
            return

        # Freeze this batch before opening the dialog or creating any new output files.
        operation = self.operation.currentText()
        sources = self.paths[:] if all_eligible else self.selected_paths()

        single_selected = not all_eligible and len(sources) == 1

        # Retain the user selection, but queue only inputs supported by this operation.
        ineligible = sum(not eligible(path, operation) for path in sources)
        sources = [path for path in sources if eligible(path, operation)]
        if not sources:
            QMessageBox.information(
                self, "No eligible files", "Select files marked Eligible for this operation."
            )
            return

        dialog = DIALOGS[operation](self)
        if operation in TRIAL_OPERATIONS:
            duration = 0
            reason = "Trial mode requires a single selected video; use Process selected."
            if single_selected:
                try:
                    duration = self.runner.probe(sources[0]).duration
                    reason = "Trial mode requires a video with a known duration."
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    reason = f"Cannot determine video duration: {error}"
            dialog.configure_trial(duration, reason)
        if not dialog.exec():
            return

        settings = dialog.settings()
        if ineligible:
            self.log.appendPlainText(f"Excluded {ineligible} ineligible file(s).")

        self.counts.setText("0 completed • 0 skipped • 0 failed • 0 cancelled")

        # The shared runner may still carry a cancellation request from the previous batch.
        self.runner.cancelled.clear()
        self.worker = BatchWorker(
            sources, operation, settings, self.runner, trial=dialog.trial_range()
        )

        # Qt delivers these signals to GUI-thread slots; workers never mutate widgets.
        self.worker.progress.connect(self.report_progress)
        self.worker.outcomes.connect(self.report_results)
        self.worker.finished.connect(self.batch_finished)
        self.cancel_button.setEnabled(True)
        self.operation.setEnabled(False)
        self.folder_button.setEnabled(False)
        self.refresh()
        self.worker.start()

    def report_progress(self, filename: str, percent: float, message: str) -> None:
        """
        Display phase progress and append diagnostics without touching worker state.

        :param filename: Current source filename displayed alongside the processing phase.
        :param percent: Progress percentage, -1 for diagnostics, or -2 for aggregate counts.
        :param message: Phase description, diagnostic text or aggregate outcome summary.
        """
        # Negative values multiplex count summaries and diagnostics without moving the bar.
        if percent == -2:
            self.counts.setText(message)
        elif percent < 0:
            self.log.appendPlainText(message)
        else:
            self.status.setText(f"{filename} — {message}")
            self.progress.setValue(int(percent))

    def report_results(self, results: list) -> None:
        """
        Show per-file outcomes and aggregate counts.

        :param results: Per-file outcomes returned by the sequential batch engine.
        """
        counts = {
            status: sum(result.status == status for result in results)
            for status in ("completed", "skipped", "failed", "cancelled")
        }
        for result in results:
            self.log.appendPlainText(
                f"{result.status}: {result.source.name}: {result.message} {result.output or ''}"
            )
        self.log.appendPlainText(
            " • ".join(f"{count} {status}" for status, count in counts.items())
        )

    def batch_finished(self) -> None:
        """Restore idle actions only after the thread has stopped."""
        # Only release the thread after its finished signal, never while it is still running.
        self.worker.deleteLater()
        self.worker = None
        self.cancel_button.setEnabled(False)
        self.operation.setEnabled(True)
        self.folder_button.setEnabled(True)

        # Complete a deferred close automatically once cancellation has stopped the worker.
        if self.close_requested:
            self.close()
            return
        self.refresh()

    def cancel(self) -> None:
        """Cancel active work and all queued jobs."""
        if self.runner:
            self.runner.cancel()

    def diagnostics(self) -> None:
        """Show tool versions and allow explicit executable configuration."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QTextEdit

        dialog = QDialog(self)
        dialog.setWindowTitle("ReefFrame diagnostics")
        dialog.resize(760, 550)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        controls = {}
        for tool in ("ffmpeg", "ffprobe"):
            control = QLineEdit(str(self.preferences.value(tool, "")))
            control.setPlaceholderText("Automatic discovery, or absolute executable path")
            form.addRow(tool, control)
            controls[tool] = control
        layout.addLayout(form)
        information = QTextEdit()
        information.setReadOnly(True)
        information.setPlainText(
            (
                f"FFmpeg: {self.runner.ffmpeg}\n{self.runner.version}\n"
                f"FFprobe: {self.runner.ffprobe}\n{self.runner.probe_version}"
            )
            if self.runner
            else "Install FFmpeg, then save paths to retry discovery."
        )
        layout.addWidget(information)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        # Do not replace the runner beneath an active job; new paths apply while idle only.
        if dialog.exec() and self.worker is None:
            for tool, control in controls.items():
                self.preferences.setValue(tool, control.text())
            self.check_dependencies()
            self.refresh()

    def shutdown(self) -> None:
        """Save preferences and stop the worker before application teardown."""
        self.preferences.setValue("geometry", self.saveGeometry())
        self.preferences.sync()
        if self.worker is not None:
            self.cancel()

            # Application teardown cannot destroy a QThread that still owns a child process.
            self.worker.wait()
            self.worker.deleteLater()
            self.worker = None

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Defer closing until cancellation completes; save geometry when idle.

        :param event: Qt close event accepted when idle or deferred until cancellation completes.
        """
        # Keep the event loop alive for cancellation and the finished signal before closing.
        if self.worker is not None:
            self.close_requested = True
            self.cancel()
            self.status.setText("Cancelling processing and quitting…")
            event.ignore()
            return

        self.preferences.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)
