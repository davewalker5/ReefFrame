"""Dedicated dialogs and GUI-thread worker boundary checks."""

import pytest

from config.settings import OPERATIONS, load_default
from gui.main_window import DIALOGS


@pytest.mark.parametrize("operation", OPERATIONS)
def test_dialogs(application, operation):
    """
    Each independent form restores defaults and validates all shipped settings.

    :param application: Shared offscreen Qt application fixture.
    :param operation: Registered operation name used to select defaults and processing behaviour.
    """
    dialog = DIALOGS[operation]()
    assert dialog.settings() == load_default(operation)
    dialog.controls["overwrite"].setChecked(True)
    dialog.restore_defaults()
    assert not dialog.settings()["overwrite"]
    if operation == "snapshot":
        dialog.controls["timestamp"].setText("bad")
        dialog.accept()
        assert "Timestamp" in dialog.error.text()
    dialog.close()


def test_selection_and_worker_state(application, tmp_path, monkeypatch):
    """
    Sorted selections retain source identities and busy state disables both starts.

    :param application: Shared offscreen Qt application fixture.
    :param tmp_path: Isolated temporary directory supplied by pytest.
    :param monkeypatch: Pytest fixture for restoring patched attributes after the test.
    """
    from gui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "check_dependencies", lambda self: None)
    window = MainWindow()
    for name in ("a.mp4", "b.mp4", "z.MOV"):
        (tmp_path / name).touch()
    window.folder = tmp_path
    window.operation.setCurrentText("reduce")
    window.refresh()
    window.table.selectRow(1)
    assert window.selected_paths() == [tmp_path / "b.mp4"]
    window.table.sortItems(0)
    assert window.selected_paths() == [tmp_path / "b.mp4"]
    window.worker = object()
    window.refresh()
    assert not window.all_button.isEnabled()
    assert not window.selected_button.isEnabled()
    window.worker = None
    window.hide()


@pytest.mark.parametrize("operation", ["snapshot", "gif", "reduce"])
def test_comparison_not_available(application, operation):
    """
    Legacy presets cannot enable comparison in dialogs without that option.

    :param application: Shared offscreen Qt application fixture.
    :param operation: Registered operation name used to select defaults and processing behaviour.
    """
    dialog = DIALOGS[operation]()
    assert "comparison" not in dialog.controls
    dialog.set_values(load_default(operation) | {"comparison": True})
    assert dialog.settings()["comparison"] is False
    dialog.close()


@pytest.mark.parametrize("sort_column", [0, 3])
@pytest.mark.parametrize("selected_names", [("a.mp4",), ("a.mp4", "z.MOV"), ()])
def test_operation_changes_preserve_selection(
    application, tmp_path, monkeypatch, sort_column, selected_names
):
    """
    Rebuilding a sorted table must not transfer selection to different file rows.

    :param application: Shared offscreen Qt application fixture.
    :param tmp_path: Isolated temporary directory supplied by pytest.
    :param monkeypatch: Pytest fixture for restoring patched attributes after the test.
    :param sort_column: File-table column used to reorder rows before changing operations.
    :param selected_names: Source filenames whose selection must survive table refreshes.
    """
    from PySide6.QtCore import Qt

    from gui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "check_dependencies", lambda self: None)
    window = MainWindow()
    for name in ("a.mp4", "b.mp4", "z.MOV"):
        (tmp_path / name).touch()
    window.folder = tmp_path
    window.refresh()
    window.table.sortItems(sort_column, Qt.SortOrder.DescendingOrder)
    window.table.clearSelection()
    for row in range(window.table.rowCount()):
        if window.table.item(row, 0).text() in selected_names:
            for column in range(window.table.columnCount()):
                window.table.item(row, column).setSelected(True)
    expected = {tmp_path / name for name in selected_names}
    assert set(window.selected_paths()) == expected
    for operation in ("enhance", "convert", "reduce", "snapshot", "stabilise"):
        window.operation.setCurrentText(operation)
        assert set(window.selected_paths()) == expected
    window.refresh()
    assert set(window.selected_paths()) == expected
    window.hide()
