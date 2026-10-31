"""Trial timing, selection restrictions and real encoded output checks."""

import importlib

import pytest

from config.settings import load_default
from gui.main_window import DIALOGS
from processing.batch import run_batch
from processing.ffmpeg_runner import FFmpegRunner
from processing.trial import TRIAL_OPERATIONS, TrialRange


@pytest.mark.parametrize("operation", TRIAL_OPERATIONS)
def test_trial_dialog(application, operation):
    """Keep trials opt-in, disable unavailable trials and leave preset settings unchanged.

    :param application: Shared offscreen Qt application fixture.
    :param operation: Supported trial operation.
    """
    dialog = DIALOGS[operation]()
    assert not dialog.trial_group.isEnabled()
    dialog.configure_trial(90.25)
    assert dialog.trial_start.text() == "00:00:00"
    assert dialog.trial_end.text() == "00:01:30.250"
    assert dialog.trial_range() is None
    assert not dialog.trial_times.isEnabled()
    dialog.trial_enabled.setChecked(True)
    assert dialog.trial_times.isEnabled()
    dialog.trial_start.setText("00:00:12.125")
    dialog.trial_end.setText("00:00:15.500")
    assert dialog.trial_range() == TrialRange(12.125, 15.5)
    assert dialog.settings() == load_default(operation)
    for invalid in ("bad", "00:01:31", "00:00:12.125", "00:00:11"):
        dialog.trial_end.setText(invalid)
        with pytest.raises(ValueError):
            dialog.trial_range()
    dialog.restore_defaults()
    assert dialog.trial_range() is None
    dialog.trial_enabled.setChecked(True)
    dialog.configure_trial(reason="Select one file")
    assert not dialog.trial_group.isEnabled()
    assert not dialog.trial_times.isEnabled()
    assert dialog.trial_range() is None
    dialog.close()


@pytest.mark.parametrize("operation", TRIAL_OPERATIONS)
@pytest.mark.parametrize("comparison", [False, True])
def test_trial_phase_inputs(operation, comparison):
    """Seek every original-source input equally, without seeking the stable intermediate.

    :param operation: Supported trial operation.
    :param comparison: Whether to include a comparison render.
    """
    from pathlib import Path

    source, destination = Path("/tmp/source.mp4"), Path("/tmp/result.mp4")
    module = importlib.import_module("processing." + operation)
    settings = load_default(operation) | {"comparison": comparison}
    phases = (
        module.build_phases(source, destination, settings)
        if operation == "stabilise"
        else [("Rendering", module.build_arguments(source, destination, settings))]
    )
    for _, arguments in phases:
        args = TrialRange(12.5, 18).apply(arguments, str(source))
        index = args.index(str(source))
        assert args[index - 5 : index] == ["-ss", "12.5", "-t", "5.5", "-i"]
        if "stable.mkv" in args and args[-1] != "stable.mkv":
            index = args.index("stable.mkv")
            assert args[index - 2 : index] == [str(source), "-i"]


@pytest.mark.parametrize("operation", TRIAL_OPERATIONS)
@pytest.mark.parametrize("comparison", [False, True])
@pytest.mark.parametrize("clip", [False, True], indirect=True)
def test_trial_output(clip, operation, comparison):
    """Render only a non-zero-start interval with correct duration and audio presence.

    :param clip: Generated one-second video with optional audio.
    :param operation: Supported trial operation.
    :param comparison: Whether to include original/processed comparison.
    """
    runner = FFmpegRunner()
    if reason := runner.unavailable(operation, comparison):
        pytest.skip(reason)
    settings = load_default(operation) | {"comparison": comparison, "preset": "ultrafast"}
    result = run_batch(
        [clip], operation, settings, runner, lambda *args: None, trial=TrialRange(0.25, 0.75)
    )[0]
    assert result.status == "completed", result.message
    assert "-trial-0.25s-to-0.75s" in result.output.name
    metadata = runner.probe(result.output)
    assert metadata.duration == pytest.approx(0.5, abs=0.1)
    assert metadata.audio == runner.probe(clip).audio
    assert metadata.width == (320 if comparison else 160)
    assert clip.exists()


@pytest.mark.parametrize("start,end", [(-1, 1), (1, 1), (2, 1), (0, 11), (float("nan"), 1)])
def test_invalid_trial_range(start, end):
    """Reject empty, reversed, out-of-bounds and non-finite ranges.

    :param start: Trial start in seconds.
    :param end: Trial end in seconds.
    """
    with pytest.raises(ValueError):
        TrialRange(start, end).validate(10)


def test_trial_queue_restrictions():
    """Reject trials for unsupported operations and queues other than one file."""
    from pathlib import Path

    for sources, operation in (
        ([], "enhance"),
        ([Path("a"), Path("b")], "enhance"),
        ([Path("a")], "reduce"),
    ):
        with pytest.raises(ValueError, match="requires one file"):
            run_batch(
                sources,
                operation,
                load_default(operation),
                None,
                lambda *args: None,
                trial=TrialRange(0, 1),
            )


@pytest.mark.parametrize("all_eligible,count", [(False, 1), (False, 2), (True, 1)])
def test_trial_selection_context(application, tmp_path, monkeypatch, all_eligible, count):
    """Only an explicitly selected single row enables trial controls in the launch dialog.

    :param application: Shared offscreen Qt application fixture.
    :param tmp_path: Temporary source folder.
    :param monkeypatch: Scoped replacements for dependencies and modal dialog execution.
    :param all_eligible: Whether the user requested all eligible files.
    :param count: Number of selected rows.
    """
    from types import SimpleNamespace

    from gui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "check_dependencies", lambda self: None)
    window = MainWindow()
    for name in ("a.mp4", "b.mp4"):
        (tmp_path / name).touch()
    window.folder = tmp_path
    window.operation.setCurrentText("enhance")
    window.refresh()
    window.table.clearSelection()
    for row in range(count):
        for column in range(window.table.columnCount()):
            window.table.item(row, column).setSelected(True)
    window.runner = SimpleNamespace(probe=lambda path: SimpleNamespace(duration=10))
    states = []
    monkeypatch.setattr(
        DIALOGS["enhance"],
        "exec",
        lambda self: states.append(self.trial_group.isEnabled()) or 0,
    )
    window.start_batch(all_eligible)
    assert states == [not all_eligible and count == 1]
    window.runner = None
    window.close()


def test_stabilisation_information(application, monkeypatch):
    """Expose the boundary note by tooltip and keyboard-accessible button activation.

    :param application: Shared offscreen Qt application fixture.
    :param monkeypatch: Scoped replacement of the information message box.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox, QToolButton

    dialog = DIALOGS["stabilise"]()
    dialog.configure_trial(10)
    info = dialog.findChild(QToolButton)
    assert "start and end" in info.toolTip()
    assert info.focusPolicy() == Qt.FocusPolicy.StrongFocus
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args))
    info.click()
    assert messages[0][2] == info.toolTip()
    dialog.close()


def test_custom_trial_output_and_invalid_interval(clip):
    """Keep custom full-render outputs intact and reject invalid times before rendering.

    :param clip: Generated one-second source video.
    """
    runner = FFmpegRunner()
    full_output = clip.parent / "custom.mp4"
    full_output.write_bytes(b"existing full render")
    settings = load_default("enhance") | {"output_name": "custom.mp4", "overwrite": True}
    original = clip.read_bytes()
    invalid = run_batch(
        [clip], "enhance", settings, runner, lambda *args: None, trial=TrialRange(0, 2)
    )[0]
    assert invalid.status == "failed"
    assert not (clip.parent / "custom-trial-0s-to-2s.mp4").exists()
    result = run_batch(
        [clip], "enhance", settings, runner, lambda *args: None, trial=TrialRange(0, 0.5)
    )[0]
    assert result.status == "completed", result.message
    assert result.output.name == "custom-trial-0s-to-0.5s.mp4"
    assert full_output.read_bytes() == b"existing full render"
    assert clip.read_bytes() == original
