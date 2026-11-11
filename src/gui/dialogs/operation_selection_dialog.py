"""First-step stage selection and pipeline preset import."""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config.pipeline import STAGE_ORDER
from config.preferences import remember_pipeline_selection
from config.settings import (
    OPERATION_LABELS,
    load_preset,
    preset_directory,
    remember_preset_directory,
    user_directory,
    validate,
)


class OperationSelectionDialog(QDialog):
    """Select a non-empty pipeline without changing the caller on cancellation."""

    def __init__(self, settings: dict, parent: QWidget | None = None) -> None:
        """Create ordered checkboxes with a detached settings snapshot.

        :param settings: Current complete pipeline settings.
        :param parent: Optional owning settings dialog.
        """
        super().__init__(parent)
        self.values = validate("enhance", settings)
        self.setWindowTitle("Choose operations — ReefFrame")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose operations in their processing order:"))
        self.checkboxes = {}
        for name in STAGE_ORDER:
            checkbox = QCheckBox(OPERATION_LABELS[name])
            checkbox.setChecked(name in self.values["enabled"])
            self.checkboxes[name] = checkbox
            layout.addWidget(checkbox)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        load = QPushButton("Load preset")
        load.clicked.connect(self.import_preset)
        layout.addWidget(load)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continue")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def import_preset(self) -> None:
        """Load a validated pipeline preset without partially changing selections."""
        name, _ = QFileDialog.getOpenFileName(
            self, "Load pipeline preset", str(preset_directory(user_directory())), "JSON (*.json)"
        )
        if not name:
            return
        try:
            values = load_preset(Path(name), "enhance")
        except (ValueError, OSError) as error:
            self.error.setText(str(error))
            return
        self.values = values
        for operation, checkbox in self.checkboxes.items():
            checkbox.setChecked(operation in values["enabled"])
        self.error.clear()
        remember_preset_directory(Path(name))

    def accept(self) -> None:
        """Require at least one selected stage before continuing."""
        enabled = [name for name, checkbox in self.checkboxes.items() if checkbox.isChecked()]
        if not enabled:
            self.error.setText("Choose at least one operation.")
            return
        try:
            remember_pipeline_selection(enabled)
        except (ValueError, OSError) as error:
            self.error.setText(str(error))
            return
        self.values["enabled"] = enabled
        super().accept()
