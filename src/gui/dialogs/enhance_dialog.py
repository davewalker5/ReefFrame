"""Sectioned pipeline settings with shared trial, preset and output controls."""

from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config.pipeline import STAGE_FIELDS, STAGE_ORDER
from config.settings import OPERATION_LABELS, validate
from gui.dialogs.base_operation_dialog import BaseOperationDialog
from gui.dialogs.fields import control_value, parameter_control, set_control_value
from gui.dialogs.operation_selection_dialog import OperationSelectionDialog

PARAMETER_LABELS = {
    "shakiness": "Shakiness",
    "accuracy": "Accuracy",
    "smoothing": "Smoothing",
    "optzoom": "Automatic zoom",
    "keep_motion": "Keep motion data",
    "contrast": "Contrast",
    "brightness": "Brightness",
    "red_gain": "Red gain",
    "green_gain": "Green gain",
    "blue_gain": "Blue gain",
    "gamma": "Gamma",
    "shadow_lift": "Shadow lift",
    "shadow_range": "Shadow range",
}
SECTION_NOTES = {
    "stabilise": "Trial boundaries can differ from a full-clip stabilisation. Assess the middle.",
    "dehaze": "Initial contrast and brightness. Combined contrast adjustments may clip detail.",
    "colour": "1 is neutral. Strong gains may amplify noise or clip highlights.",
    "gamma": "Shadow lift fades smoothly to zero at the selected tonal range.",
    "contrast": "1 is neutral. Above 1 increases contrast and may obscure shadows.",
    "reduce": "Controls final output compression; a smaller file is not guaranteed.",
}


class EnhanceDialog(BaseOperationDialog):
    """Configure a selected subset of the six ordered pipeline operations."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Build scrolling sections and retain fixed, reachable action buttons.

        :param parent: Optional owning window.
        """
        super().__init__("enhance", parent)
        buttons = self.findChild(QDialogButtonBox)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Process")
        self.setMinimumWidth(640)
        available = self.screen().availableGeometry()
        self.resize(min(900, available.width() - 60), min(850, available.height() - 80))
        self.update_sections()

    def add_form_container(self, layout: QVBoxLayout) -> None:
        """Place a summary above scrolling settings and keep shared actions outside.

        :param layout: Main dialog layout receiving the header and settings body.
        """
        body = QWidget()
        body.setLayout(self.form)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(body)
        header = QWidget()
        header_layout = QHBoxLayout(header)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        header_layout.addWidget(self.summary, 1)
        change = QPushButton("Change operations…")
        change.clicked.connect(self.change_operations)
        header_layout.addWidget(change)
        layout.addWidget(header)
        layout.addWidget(self.scroll, 1)

    def build_parameters(self) -> None:
        """Build reusable stage controls and exactly one visible encoding pair."""
        self.pipeline_values = validate("enhance", self.values)
        self.body_form = self.form
        self.stage_controls = {}
        self.stage_sections = {}
        grid_widget = QWidget()
        self.section_grid = QGridLayout(grid_widget)
        self.section_grid.setContentsMargins(0, 0, 0, 0)
        self.section_grid.setColumnStretch(0, 1)
        self.section_grid.setColumnStretch(1, 1)
        self.body_form.addRow(grid_widget)
        for name in STAGE_ORDER:
            group = QGroupBox(OPERATION_LABELS[name], grid_widget)
            form = QFormLayout(group)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            self.stage_sections[name] = group
            controls = {}
            for key in STAGE_FIELDS[name]:
                label = PARAMETER_LABELS[key]
                control = parameter_control(key, self.values["stages"][name][key], label)
                if key == "optzoom":
                    control.setToolTip("0: off; 1: adaptive zoom; 2: static zoom.")
                elif key == "gamma":
                    control.setToolTip("0.1–3.0; 1 is neutral. Above 1 lightens midtones.")
                controls[key] = control
                form.addRow(label, control)
            note = QLabel(SECTION_NOTES[name])
            note.setWordWrap(True)
            form.addRow(note)
            self.stage_controls[name] = controls
        self.normal_encoding, self.normal_controls = self.encoding_group("Output encoding", False)
        self.body_form.addRow(self.normal_encoding)
        reduction_form = self.stage_sections["reduce"].layout()
        self.reduction_controls = self.add_encoding_fields(reduction_form, True)
        shared = QGroupBox("Shared output options")
        self.form = QFormLayout(shared)
        self.body_form.addRow(shared)
        self.add_field("audio_policy", "Audio policy")
        self.controls["audio_policy"].setToolTip(
            "Copy, AAC or remove. Trials encode copied audio as AAC for accurate boundaries."
        )

    def encoding_group(self, title: str, reduced: bool) -> tuple[QGroupBox, dict]:
        """Create the normal output encoding section.

        :param title: Visible section title.
        :param reduced: Whether to use the retained reduction settings.
        :return: Encoding group and its two controls.
        """
        group = QGroupBox(title)
        return group, self.add_encoding_fields(QFormLayout(group), reduced)

    def add_encoding_fields(self, form: QFormLayout, reduced: bool) -> dict:
        """Create a retained encoder pair with existing parameter ranges.

        :param form: Destination section form.
        :param reduced: Whether to initialise from reduction settings.
        :return: Mapping of encoder keys to controls.
        """
        controls = {}
        for key, label in (("crf", "CRF"), ("preset", "Encoding preset")):
            stored_key = "reduction_" + key if reduced else key
            control = parameter_control(key, self.values[stored_key], label)
            controls[key] = control
            form.addRow(label, control)
        return controls

    def update_sections(self) -> None:
        """Reflow selected sections in processing order and update encoding visibility."""
        enabled = self.pipeline_values["enabled"]
        for group in self.stage_sections.values():
            self.section_grid.removeWidget(group)
            group.hide()
        for index, name in enumerate(enabled):
            group = self.stage_sections[name]
            self.section_grid.addWidget(group, index // 2, index % 2)
            group.show()
        self.normal_encoding.setVisible("reduce" not in enabled)
        self.summary.setText(f"{len(enabled)} operations selected — applied in the order shown")

    def settings(self) -> dict:
        """Collect stage values and shared options without persisting trial controls.

        :return: Complete detached and validated pipeline settings.
        :raises ValueError: If the current controls are invalid.
        """
        values = validate("enhance", self.pipeline_values)
        for name, controls in self.stage_controls.items():
            values["stages"][name] = {
                key: control_value(control) for key, control in controls.items()
            }
        for prefix, controls in (
            ("", self.normal_controls),
            ("reduction_", self.reduction_controls),
        ):
            for key, control in controls.items():
                values[prefix + key] = control_value(control)
        for key, control in self.controls.items():
            values[key] = control_value(control)
        return validate("enhance", values)

    def set_values(self, values: dict) -> None:
        """Validate all imported values before replacing any widget state.

        :param values: Complete pipeline settings to display.
        :raises ValueError: If any setting is invalid.
        """
        values = validate("enhance", values)
        self.pipeline_values = values
        for name, controls in self.stage_controls.items():
            for key, control in controls.items():
                set_control_value(control, values["stages"][name][key])
        for prefix, controls in (
            ("", self.normal_controls),
            ("reduction_", self.reduction_controls),
        ):
            for key, control in controls.items():
                set_control_value(control, values[prefix + key])
        for key, control in self.controls.items():
            set_control_value(control, values[key])
        self.update_sections()

    def choose_operations(self) -> bool:
        """Run stage selection, leaving all values intact if cancelled.

        :return: Whether a selection or preset was accepted.
        """
        try:
            values = self.settings()
        except ValueError as error:
            self.error.setText(str(error))
            return False
        selection = OperationSelectionDialog(values, self)
        if not selection.exec():
            return False
        self.set_values(selection.values)
        return True

    def change_operations(self) -> None:
        """Change selected stages while retaining shared settings and per-run trial state."""
        self.choose_operations()

    def exec(self) -> int:
        """Show operation selection before entering the settings dialog.

        :return: Accepted only when both selection and settings are confirmed.
        """
        if not self.choose_operations():
            return 0
        return super().exec()
