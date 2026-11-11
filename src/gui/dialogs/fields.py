"""Reusable typed parameter widgets for standalone and sectioned settings forms."""

from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit, QSpinBox, QWidget

from config.settings import CHOICES, RANGES


def parameter_control(key: str, default: object, label: str) -> QWidget:
    """Create an accessible control using the existing settings conventions.

    :param key: Parameter key identifying supported ranges and choices.
    :param default: Default value defining the control's type.
    :param label: Accessible parameter label.
    :return: Initialised parameter widget.
    """
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
    control.setAccessibleName(label)
    set_control_value(control, default)
    return control


def set_control_value(control: QWidget, value: object) -> None:
    """Populate one typed parameter widget.

    :param control: Widget returned by parameter_control.
    :param value: Validated value matching the widget type.
    """
    if isinstance(control, QComboBox):
        control.setCurrentText(value)
    elif isinstance(control, QCheckBox):
        control.setChecked(value)
    elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
        control.setValue(value)
    else:
        control.setText(value)


def control_value(control: QWidget) -> str | bool | int | float:
    """Read the current value of a typed parameter widget.

    :param control: Widget returned by parameter_control.
    :return: Current widget value.
    """
    if isinstance(control, QComboBox):
        return control.currentText()
    if isinstance(control, QCheckBox):
        return control.isChecked()
    if isinstance(control, (QSpinBox, QDoubleSpinBox)):
        return control.value()
    return control.text()
