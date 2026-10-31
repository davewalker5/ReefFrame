"""Shared preset and output controls for dedicated operation forms."""

import math
import re
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from config.settings import (
    CHOICES,
    RANGES,
    load_default,
    load_preset,
    save_preset,
    user_directory,
    validate,
)
from processing.trial import TRIAL_OPERATIONS, TrialRange


class BaseOperationDialog(QDialog):
    """Supply shared controls; subclasses explicitly define their operation parameter layout."""

    def __init__(self, operation: str, parent: QWidget | None = None) -> None:
        """
        Create a labelled parameter dialog from validated shipped defaults.

        :param operation: Registered operation name used to select defaults and processing
            behaviour.
        :param parent: Optional parent widget controlling dialog ownership.
        """
        super().__init__(parent)
        self.operation = operation
        self.values = load_default(operation)
        self.controls = {}
        self.setWindowTitle(f"{operation.title()} settings — ReefFrame")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        self.form = QFormLayout()
        layout.addLayout(self.form)
        self.build_parameters()
        if operation not in ("snapshot", "gif", "reduce"):
            self.add_field("comparison", "Original left / processed right")
            self.controls["comparison"].setToolTip(
                "Video comparisons fit within 1920 × 1080 for smooth playback. "
                "Aspect ratio and frame timing are preserved."
            )
        self.trial_duration = 0.0
        if operation in TRIAL_OPERATIONS:
            self.build_trial_controls()
        self.add_field("overwrite", "Overwrite existing outputs")
        self.add_field("output_name", "Output filename (blank = automatic)")
        self.controls["output_name"].setToolTip(
            "A filename only. For batches, leave blank to retain each source stem."
        )
        row = QHBoxLayout()
        for label, callback in (
            ("Load default", self.restore_defaults),
            ("Load preset", self.import_preset),
            ("Save preset as…", self.export_preset),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.set_values(self.values)

    def build_trial_controls(self) -> None:
        """Add per-run trial controls, disabled until a single source is supplied."""
        self.trial_group = QWidget()
        row = QHBoxLayout(self.trial_group)
        row.setContentsMargins(0, 0, 0, 0)
        self.trial_enabled = QCheckBox("Trial mode")
        row.addWidget(self.trial_enabled)
        if self.operation == "stabilise":
            note = (
                "Stabilisation near the start and end of a trial may differ from full-clip "
                "processing. Choose a slightly longer section to assess the middle."
            )
            info = QLabel("ⓘ")
            info.setAccessibleName("About stabilisation trials")
            info.setToolTip(note)
            info.setAccessibleDescription(note)
            row.addWidget(info)
        row.addStretch()
        self.form.addRow(self.trial_group)
        self.trial_times = QWidget()
        times = QFormLayout(self.trial_times)
        times.setContentsMargins(0, 0, 0, 0)
        self.trial_start = QLineEdit("00:00:00")
        self.trial_end = QLineEdit("00:00:00")
        for label, control in (("Start time", self.trial_start), ("End time", self.trial_end)):
            control.setAccessibleName(label)
            control.setToolTip("HH:MM:SS or HH:MM:SS.mmm")
            times.addRow(label, control)
        self.form.addRow(self.trial_times)
        self.trial_enabled.toggled.connect(self.trial_times.setEnabled)
        self.trial_times.setEnabled(False)
        self.trial_group.setEnabled(False)
        self.trial_group.setToolTip("Trial mode requires a single selected video.")

    @staticmethod
    def format_trial_time(seconds: float) -> str:
        """Format a duration without rounding beyond the source endpoint.

        :param seconds: Source duration in seconds.
        :return: Timestamp in HH:MM:SS.mmm form.
        """
        milliseconds = math.floor(seconds * 1000)
        hours, remainder = divmod(milliseconds, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        return f"{hours:02}:{minutes:02}:{remainder // 1000:02}.{remainder % 1000:03}"

    def configure_trial(self, duration: float = 0, reason: str = "") -> None:
        """Enable trial mode only for a known-duration, explicitly selected single file.

        :param duration: Probed duration of the selected file, or zero when unavailable.
        :param reason: Explanation when trial mode is unavailable.
        """
        if self.operation not in TRIAL_OPERATIONS:
            return
        available = math.isfinite(duration) and duration > 0
        self.trial_duration = duration if available else 0
        self.trial_enabled.setChecked(False)
        self.trial_group.setEnabled(available)
        self.trial_group.setToolTip(
            "Process a short section to check settings." if available else reason
        )
        self.trial_end.setText(self.format_trial_time(self.trial_duration))
        self.trial_times.setEnabled(False)
        self.trial_times.setToolTip("" if available else reason)

    def trial_range(self) -> TrialRange | None:
        """Read and validate per-run trial controls without changing preset settings.

        :return: Selected trial interval, or None for whole-video processing.
        :raises ValueError: If enabled trial timestamps are malformed or outside the video.
        """
        if self.operation not in TRIAL_OPERATIONS or not self.trial_group.isEnabled():
            return None
        if not self.trial_enabled.isChecked():
            return None
        seconds = []
        for control in (self.trial_start, self.trial_end):
            text = control.text().strip()
            if not re.fullmatch(r"[0-9]{2,}:[0-5][0-9]:[0-5][0-9](\.[0-9]{1,3})?", text):
                raise ValueError("Trial times must use HH:MM:SS or HH:MM:SS.mmm")
            hours, minutes, rest = text.split(":")
            seconds.append(int(hours) * 3600 + int(minutes) * 60 + float(rest))
        trial = TrialRange(*seconds)
        trial.validate(self.trial_duration)
        return trial

    def build_parameters(self) -> None:
        """
        Require each operation module to define its own parameter layout.

        :raises NotImplementedError: If a subclass does not provide its operation layout.
        """
        raise NotImplementedError

    def add_field(self, key: str, label: str) -> None:
        """
        Add an accessible typed parameter control with its supported range.

        :param key: Settings key identifying the control and its default value.
        :param label: Visible, accessible label for the parameter control.
        """
        default = self.values[key]
        if key in CHOICES:
            control = QComboBox()
            control.addItems(CHOICES[key])
        elif isinstance(default, bool):
            control = QCheckBox()
        elif isinstance(default, (int, float)):
            control = QDoubleSpinBox() if isinstance(default, float) else QSpinBox()
            control.setRange(*RANGES[key])
            if isinstance(default, float):
                control.setDecimals(3)
                control.setSingleStep(0.01)
            control.setToolTip(f"Allowed range: {RANGES[key][0]} to {RANGES[key][1]}")
        else:
            control = QLineEdit()
        self.controls[key] = control
        self.form.addRow(label, control)

    def set_values(self, values: dict) -> None:
        """
        Populate controls from complete validated settings.

        :param values: Complete settings to validate and display in the controls.
        :raises ValueError: If the supplied settings are invalid.
        """
        for key, value in validate(self.operation, values).items():
            if key not in self.controls:
                continue
            control = self.controls[key]
            if isinstance(control, QComboBox):
                control.setCurrentText(value)
            elif isinstance(control, QCheckBox):
                control.setChecked(value)
            elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
                control.setValue(value)
            else:
                control.setText(value)

    def settings(self) -> dict:
        """
        Return validated current settings or raise ValueError.

        :return: Validated current control values, with unsupported comparison controls left
            disabled.
        :raises ValueError: If the current controls do not form valid operation settings.
        """
        values = load_default(self.operation)
        for key, control in self.controls.items():
            if isinstance(control, QComboBox):
                values[key] = control.currentText()
            elif isinstance(control, QCheckBox):
                values[key] = control.isChecked()
            elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
                values[key] = control.value()
            else:
                values[key] = control.text()
        return validate(self.operation, values)

    def accept(self) -> None:
        """Keep the dialog open and display actionable validation errors."""
        try:
            self.settings()
            self.trial_range()
        except ValueError as error:
            self.error.setText(str(error))
            return
        super().accept()

    def restore_defaults(self) -> None:
        """Restore immutable shipped defaults."""
        self.set_values(load_default(self.operation))
        if self.operation in TRIAL_OPERATIONS:
            self.trial_enabled.setChecked(False)
            self.trial_start.setText("00:00:00")
            self.trial_end.setText(self.format_trial_time(self.trial_duration))

    def import_preset(self) -> None:
        """Import a named JSON preset, displaying invalid data errors."""
        name, _ = QFileDialog.getOpenFileName(
            self, "Load preset", str(user_directory()), "JSON (*.json)"
        )
        if name:
            try:
                self.set_values(load_preset(Path(name), self.operation))
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Cannot load preset", str(error))

    def export_preset(self) -> None:
        """Export validated settings to a user-selected JSON file."""
        directory = user_directory() / "presets"
        directory.mkdir(parents=True, exist_ok=True)
        name, _ = QFileDialog.getSaveFileName(
            self, "Save preset", str(directory / (self.operation + ".json")), "JSON (*.json)"
        )
        if name:
            try:
                save_preset(Path(name), self.operation, self.settings())
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Cannot save preset", str(error))
