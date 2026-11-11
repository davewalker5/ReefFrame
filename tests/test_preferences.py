"""Persistent processing defaults, independent contexts and Qt settings location."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, QStandardPaths
from PySide6.QtWidgets import QApplication, QDialog

from config import preferences, settings
from config.preferences import (
    load_operation_settings,
    remember_operation_settings,
    remember_pipeline_selection,
    user_preferences,
)
from config.settings import OPERATIONS, load_default
from gui.dialogs.enhance_dialog import EnhanceDialog
from gui.dialogs.operation_selection_dialog import OperationSelectionDialog
from gui.main_window import DIALOGS

PARAMETER_CHANGES = {
    "convert": ("crf", 23),
    "dehaze": ("contrast", 1.5),
    "reduce": ("crf", 30),
    "gif": ("fps", 15),
    "snapshot": ("timestamp", "00:00:01"),
    "stabilise": ("smoothing", 30),
    "gamma": ("gamma", 1.5),
    "colour": ("blue_gain", 0.7),
    "contrast": ("contrast", 1.2),
}


def test_initial_pipeline_selection(application: QApplication) -> None:
    """Fresh settings select Stabilise, Dehaze and Reduce in processing order.

    :param application: Shared QApplication.
    """
    expected = ["stabilise", "dehaze", "reduce"]
    assert load_default("enhance")["enabled"] == expected
    dialog = EnhanceDialog()
    assert dialog.settings()["enabled"] == expected
    selection = OperationSelectionDialog(dialog.settings())
    assert [
        name for name, checkbox in selection.checkboxes.items() if checkbox.isChecked()
    ] == expected
    selection.close()
    dialog.close()


@pytest.mark.parametrize("operation", OPERATIONS)
def test_confirmed_settings_reopen(application: QApplication, operation: str) -> None:
    """All dialogs restore confirmed processing values but reset per-run output controls.

    :param application: Shared QApplication.
    :param operation: Operation whose dialog is reopened.
    """
    dialog = DIALOGS[operation]()
    values = load_default(operation)
    if operation == "enhance":
        values["enabled"] = ["gamma", "reduce"]
        values["stages"]["gamma"]["gamma"] = 1.4
        values["stages"]["colour"]["blue_gain"] = 0.6
        values.update(crf=20, reduction_crf=29, audio_policy="aac")
    else:
        key, value = PARAMETER_CHANGES[operation]
        values[key] = value
    values.update(output_name="temporary-output", overwrite=True)
    dialog.set_values(values)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    reopened = DIALOGS[operation]()
    expected = values | {"output_name": "", "overwrite": False}
    assert reopened.settings() == expected
    assert load_operation_settings(operation) == expected
    dialog.close()
    reopened.close()


def test_pipeline_selection_remembered_on_continue(application: QApplication) -> None:
    """Continue remembers selection without committing unconfirmed parameter edits.

    :param application: Shared QApplication.
    """
    previous = load_default("enhance")
    previous["stages"]["gamma"]["gamma"] = 1.2
    remember_operation_settings("enhance", previous)
    pending = load_operation_settings("enhance")
    pending["stages"]["gamma"]["gamma"] = 2.0
    selection = OperationSelectionDialog(pending)
    for name, checkbox in selection.checkboxes.items():
        checkbox.setChecked(name in ("colour", "gamma"))
    selection.accept()
    restored = load_operation_settings("enhance")
    assert restored["enabled"] == ["colour", "gamma"]
    assert restored["stages"]["gamma"]["gamma"] == 1.2
    reopened = EnhanceDialog()
    assert reopened.settings() == restored
    selection.close()
    reopened.close()


def test_cancel_does_not_replace_preferences(application: QApplication) -> None:
    """Rejecting settings or selections leaves confirmed values intact.

    :param application: Shared QApplication.
    """
    values = load_default("colour") | {"blue_gain": 0.8}
    remember_operation_settings("colour", values)
    dialog = DIALOGS["colour"]()
    dialog.controls["blue_gain"].setValue(0.3)
    dialog.reject()
    assert load_operation_settings("colour") == values
    selection = OperationSelectionDialog(load_default("enhance"))
    selection.checkboxes["gamma"].setChecked(True)
    selection.reject()
    assert load_operation_settings("enhance") == load_default("enhance")
    selection.close()
    dialog.close()


def test_pipeline_and_standalone_are_independent(application: QApplication) -> None:
    """Changing one context does not overwrite the other context's process settings.

    :param application: Shared QApplication.
    """
    standalone = load_default("gamma") | {"gamma": 1.5}
    remember_operation_settings("gamma", standalone)
    pipeline = load_default("enhance")
    pipeline["stages"]["gamma"]["gamma"] = 2.0
    remember_operation_settings("enhance", pipeline)
    assert DIALOGS["gamma"]().settings()["gamma"] == 1.5
    assert EnhanceDialog().settings()["stages"]["gamma"]["gamma"] == 2.0
    remember_pipeline_selection(["gamma"])
    assert load_operation_settings("enhance")["stages"]["gamma"]["gamma"] == 2.0
    assert load_operation_settings("gamma") == standalone


def test_trial_state_is_not_remembered(application: QApplication) -> None:
    """Confirming a trial stores parameters without carrying its interval into another video.

    :param application: Shared QApplication.
    """
    dialog = DIALOGS["gamma"]()
    dialog.configure_trial(10)
    dialog.trial_enabled.setChecked(True)
    dialog.trial_start.setText("00:00:01")
    dialog.trial_end.setText("00:00:02")
    dialog.controls["gamma"].setValue(1.3)
    dialog.accept()
    reopened = DIALOGS["gamma"]()
    reopened.configure_trial(20)
    assert reopened.settings()["gamma"] == 1.3
    assert reopened.trial_range() is None
    assert reopened.trial_start.text() == "00:00:00"
    dialog.close()
    reopened.close()


@pytest.mark.parametrize("stored", ["{", "[]", "null", '{"version": 99, "settings": {}}'])
def test_invalid_preferences_fall_back(stored: str, caplog: pytest.LogCaptureFixture) -> None:
    """Invalid or obsolete saved data restores defaults and produces a diagnostic.

    :param stored: Malformed remembered settings JSON.
    :param caplog: Captured application logging.
    """
    handle = user_preferences()
    handle.setValue("operations/enhance", stored)
    handle.sync()
    assert load_operation_settings("enhance") == load_default("enhance")
    assert "Ignoring invalid remembered enhance settings" in caplog.text
    assert user_preferences().value("operations/enhance") == stored


def test_invalid_saved_parameters_fall_back() -> None:
    """Stored parameters are checked against current ranges before displaying a dialog."""
    values = load_default("gamma") | {"gamma": -1}
    handle = user_preferences()
    handle.setValue("operations/gamma", json.dumps({"version": 1, "settings": values}))
    handle.sync()
    assert load_operation_settings("gamma") == load_default("gamma")


def test_settings_survive_new_process() -> None:
    """A fresh Python process reads the flushed INI values rather than a Qt memory cache."""
    values = load_default("enhance")
    values["enabled"] = ["colour", "gamma"]
    values["stages"]["colour"]["blue_gain"] = 0.65
    remember_operation_settings("enhance", values)
    source = Path(__file__).resolve().parents[1] / "src"
    script = """
import json
import sys
from pathlib import Path
from config import settings
from config.preferences import load_operation_settings
settings.user_directory = lambda: Path(sys.argv[1])
print(json.dumps(load_operation_settings("enhance")))
"""
    result = subprocess.check_output(
        [sys.executable, "-c", script, str(settings.user_directory())],
        env=os.environ | {"PYTHONPATH": str(source)},
        text=True,
    )
    assert json.loads(result) == values


def test_qt_preferences_location() -> None:
    """Use the same Qt AppConfigLocation file as existing window and preset preferences."""
    directory = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    )
    assert Path(user_preferences().fileName()) == directory / "preferences.ini"
    handle = user_preferences()
    handle.setValue("folder", "existing folder preference")
    handle.sync()
    remember_operation_settings("contrast", load_default("contrast") | {"contrast": 1.4})
    assert user_preferences().value("folder") == "existing folder preference"


def test_write_failure_keeps_dialog_open(
    application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preference write failures produce inline errors instead of falsely confirming a save.

    :param application: Shared QApplication.
    :param monkeypatch: Scoped preferences handle replacement.
    :return: None; assertions verify that confirmation is blocked on a failed write.
    """

    class UnwritablePreferences:
        """Minimal failing QSettings interface for a deterministic write failure."""

        def setValue(self, key: str, value: str) -> None:
            """Accept an in-memory value without writing a file.

            :param key: Unused preferences key.
            :param value: Unused serialised settings value.
            """

        def sync(self) -> None:
            """Simulate a failed disk flush."""

        def status(self) -> QSettings.Status:
            """Return the same status as an inaccessible preferences file.

            :return: Access error status.
            """
            return QSettings.Status.AccessError

    dialog = DIALOGS["gamma"]()
    monkeypatch.setattr(preferences, "user_preferences", UnwritablePreferences)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert "Cannot save processing preferences" in dialog.error.text()
    dialog.close()


@pytest.mark.parametrize("operation", ["gamma", "enhance"])
def test_integer_saved_float_keeps_decimal_control(
    application: QApplication, operation: str
) -> None:
    """JSON integer representations of float parameters retain fractional editing precision.

    :param application: Shared QApplication.
    :param operation: Standalone gamma or pipeline context.
    """
    from PySide6.QtWidgets import QDoubleSpinBox

    values = load_default(operation)
    if operation == "enhance":
        values["stages"]["gamma"]["gamma"] = 2
    else:
        values["gamma"] = 2
    remember_operation_settings(operation, values)
    dialog = DIALOGS[operation]()
    control = (
        dialog.stage_controls["gamma"]["gamma"]
        if operation == "enhance"
        else dialog.controls["gamma"]
    )
    assert isinstance(control, QDoubleSpinBox)
    control.setValue(1.25)
    settings = dialog.settings()
    assert (
        settings["stages"]["gamma"]["gamma"] if operation == "enhance" else settings["gamma"]
    ) == 1.25
    dialog.close()
