"""Pipeline schema, deterministic plans, selection workflow and real media integration."""

import itertools
import json
import subprocess
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from config.pipeline import STAGE_ORDER, PipelineConfiguration
from config.settings import load_default, load_preset, save_preset, validate
from gui.dialogs.enhance_dialog import EnhanceDialog
from gui.dialogs.operation_selection_dialog import OperationSelectionDialog
from processing.batch import run_batch
from processing.enhance import FILTER_BUILDERS, build_plan, required_filters
from processing.ffmpeg_runner import CancelledError, FFmpegRunner
from processing.trial import TrialRange

SUBSETS = tuple(
    subset
    for count in range(1, len(STAGE_ORDER) + 1)
    for subset in itertools.combinations(STAGE_ORDER, count)
)


def pipeline_settings(enabled: tuple[str, ...] = STAGE_ORDER) -> dict:
    """Create visibly active pipeline settings with quick test encoding.

    :param enabled: Stage selection; intentionally not required to be ordered.
    :return: Fresh complete pipeline configuration dictionary.
    """
    settings = load_default("enhance")
    settings["enabled"] = list(enabled)
    settings["stages"]["gamma"].update(gamma=1.2, shadow_lift=0.15)
    settings["stages"]["colour"]["blue_gain"] = 0.7
    settings["stages"]["contrast"]["contrast"] = 1.1
    settings.update(preset="ultrafast", reduction_preset="ultrafast")
    return settings


@pytest.fixture
def pipeline_runner() -> FFmpegRunner:
    """Prefer a local full FFmpeg build so VidStab paths are actually exercised.

    :return: Runner for the available full build, or the normal discovered build.
    """
    full = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
    return FFmpegRunner(str(full) if full.is_file() else "")


@pytest.mark.parametrize("enabled", SUBSETS)
@pytest.mark.parametrize("comparison", [False, True])
def test_all_pipeline_plans(enabled: tuple[str, ...], comparison: bool) -> None:
    """Every subset has canonical filter order and exactly one encoded video output.

    :param enabled: One of all 63 non-empty stage subsets.
    :param comparison: Whether to split original and processed branches.
    """
    settings = pipeline_settings(tuple(reversed(enabled))) | {"comparison": comparison}
    original = deepcopy(settings)
    source, destination = Path("input.mp4"), Path("output.mp4")
    plan = build_plan(source, destination, settings)
    expected = tuple(
        FILTER_BUILDERS[name](settings["stages"][name])
        for name in STAGE_ORDER
        if name in enabled and name in FILTER_BUILDERS
    )
    assert plan.filters == expected
    assert len(plan.phases) == (2 if "stabilise" in enabled else 1)
    assert sum(arguments.count("-c:v") for _, arguments in plan.phases) == 1
    assert all(arguments.count("-i") == 1 for _, arguments in plan.phases)
    assert all(
        "stable.mkv" not in arguments and "ffv1" not in arguments for _, arguments in plan.phases
    )
    arguments = plan.phases[-1][1]
    assert arguments[-1] == str(destination)
    assert arguments[arguments.index("-crf") + 1] == ("26" if "reduce" in enabled else "18")
    assert arguments.count("-c:a") == 1
    graph = arguments[arguments.index("-filter_complex" if comparison else "-vf") + 1]
    if comparison:
        assert graph.startswith("[0:v:0]setpts=PTS-STARTPTS,split[left][work];[work]")
        assert "[left][right]hstack" in graph
    assert "vibrance" not in graph
    assert settings == original


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": []},
        {"enabled": ["gamma", "gamma"]},
        {"enabled": ["missing"]},
        {"enabled": "gamma"},
        {"enabled": [True]},
        {"stages": []},
        {"stages": {}},
        {"crf": True},
        {"reduction_crf": 52},
        {"reduction_preset": "invalid"},
        {"audio_policy": "invalid"},
        {"comparison": 1},
        {"output_name": "../unsafe.mp4"},
        {"extra": 1},
    ],
)
def test_pipeline_invalid_schema(change: dict) -> None:
    """Reject invalid selections, shared settings and schema additions.

    :param change: Invalid top-level settings replacement.
    """
    with pytest.raises(ValueError):
        validate("enhance", pipeline_settings() | change)


@pytest.mark.parametrize(
    "operation,key,value",
    [
        ("gamma", "gamma", float("nan")),
        ("gamma", "gamma", 10**400),
        ("gamma", "shadow_range", 0),
        ("colour", "red_gain", float("inf")),
        ("contrast", "contrast", True),
        ("dehaze", "extra", 0),
        ("stabilise", "shakiness", 11),
        ("reduce", "crf", 26),
    ],
)
def test_pipeline_invalid_stage(operation: str, key: str, value: object) -> None:
    """Validate namespaced values even for currently disabled operations.

    :param operation: Stage whose parameters are invalidated.
    :param key: Invalid parameter name or value target.
    :param value: Invalid parameter value.
    """
    settings = pipeline_settings(("reduce",))
    settings["stages"][operation][key] = value
    with pytest.raises(ValueError):
        validate("enhance", settings)


def test_pipeline_preset_version_and_copy(tmp_path: Path) -> None:
    """Roundtrip nested values, detach snapshots and reject legacy Enhance explicitly.

    :param tmp_path: Isolated preset directory.
    """
    settings = pipeline_settings()
    path = tmp_path / "pipeline.json"
    save_preset(path, "enhance", settings)
    assert json.loads(path.read_text())["version"] == 2
    assert load_preset(path, "enhance") == settings
    configuration = PipelineConfiguration.from_settings(settings)
    settings["stages"]["stabilise"]["smoothing"] = 100
    assert configuration.stages[0].parameters["smoothing"] == 15
    document = json.loads(path.read_text()) | {"version": 1}
    path.write_text(json.dumps(document))
    original = path.read_bytes()
    with pytest.raises(ValueError, match="Recreate this legacy preset"):
        load_preset(path, "enhance")
    assert path.read_bytes() == original


def test_effective_capabilities() -> None:
    """Disabled and neutral filters cannot prevent a supported pipeline from running."""
    settings = load_default("enhance") | {"enabled": ["gamma", "colour", "contrast", "reduce"]}
    configuration = PipelineConfiguration.from_settings(settings)
    assert required_filters(configuration) == ("null",)
    runner = object.__new__(FFmpegRunner)
    runner.filters = "null split setpts hstack scale"
    runner.encoders = "libx264"
    assert not runner.unavailable("enhance")
    assert not runner.unavailable("enhance", False, settings)
    assert not runner.unavailable("enhance", True, settings | {"comparison": True})
    assert "eq" in runner.unavailable("enhance", False, load_default("enhance"))
    assert "vidstab" in runner.unavailable("enhance", False, pipeline_settings(("stabilise",)))
    assert "aac" in runner.unavailable("enhance", False, settings | {"audio_policy": "aac"})


def test_pipeline_sections_and_retained_values(
    application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selection changes retain disabled values, both encoder pairs and trial state.

    :param application: Shared offscreen QApplication.
    :param monkeypatch: Scoped dialog-execution replacement.
    :return: None; assertions check the retained settings and trial interval.
    """
    dialog = EnhanceDialog()
    dialog.set_values(load_default("enhance") | {"enabled": ["dehaze", "contrast"]})
    dialog.configure_trial(10)
    dialog.trial_enabled.setChecked(True)
    dialog.trial_start.setText("00:00:01")
    dialog.trial_end.setText("00:00:02")
    dialog.controls["comparison"].setChecked(True)
    dialog.controls["output_name"].setText("trial-result")
    dialog.stage_controls["colour"]["blue_gain"].setValue(0.65)
    dialog.normal_controls["crf"].setValue(20)
    dialog.reduction_controls["crf"].setValue(29)
    old_values = dialog.settings()
    assert dialog.stage_sections["gamma"].isHidden()
    assert not dialog.normal_encoding.isHidden()

    def select_reduce(self: OperationSelectionDialog) -> int:
        """Accept a Reduce-only selection in the nested modal dialog.

        :return: Accepted modal result.
        """
        for name, checkbox in self.checkboxes.items():
            checkbox.setChecked(name == "reduce")
        self.accept()
        return self.result()

    monkeypatch.setattr(OperationSelectionDialog, "exec", select_reduce)
    dialog.change_operations()
    values = dialog.settings()
    assert values["enabled"] == ["reduce"]
    assert dialog.normal_encoding.isHidden()
    assert not dialog.stage_sections["reduce"].isHidden()
    assert all(dialog.stage_sections[name].isHidden() for name in STAGE_ORDER if name != "reduce")
    assert values["crf"] == 20 and values["reduction_crf"] == 29
    assert values["stages"]["colour"]["blue_gain"] == 0.65
    assert values["output_name"] == old_values["output_name"]
    assert values["comparison"]
    assert dialog.trial_range() == TrialRange(1, 2)
    monkeypatch.setattr(OperationSelectionDialog, "exec", lambda self: 0)
    dialog.change_operations()
    assert dialog.settings() == values
    invalid = deepcopy(values)
    invalid["stages"]["gamma"]["gamma"] = -1
    with pytest.raises(ValueError):
        dialog.set_values(invalid)
    assert dialog.settings() == values
    dialog.restore_defaults()
    assert dialog.settings() == load_default("enhance")
    assert dialog.trial_range() is None
    dialog.close()


def test_selection_and_initial_workflow(
    application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty selections cannot continue, and initial selection cancel never opens settings.

    :param application: Shared offscreen QApplication.
    :param monkeypatch: Scoped modal-execution replacements.
    """
    selection = OperationSelectionDialog(load_default("enhance"))
    for checkbox in selection.checkboxes.values():
        checkbox.setChecked(False)
    selection.accept()
    assert selection.result() == QDialog.DialogCode.Rejected
    assert "at least one" in selection.error.text()
    selection.checkboxes["reduce"].setChecked(True)
    selection.accept()
    assert selection.values["enabled"] == ["reduce"]
    selection.close()
    opened = []
    monkeypatch.setattr(OperationSelectionDialog, "exec", lambda self: 0)
    monkeypatch.setattr(QDialog, "exec", lambda self: opened.append(self) or 0)
    dialog = EnhanceDialog()
    assert dialog.exec() == 0
    assert not opened
    monkeypatch.setattr(OperationSelectionDialog, "exec", lambda self: 1)
    assert dialog.exec() == 0
    assert opened == [dialog]
    dialog.close()


def test_selection_preset_import(
    application: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first-step preset import restores full settings; invalid imports remain atomic.

    :param application: Shared offscreen QApplication.
    :param tmp_path: Isolated preset and preferences directory.
    :param monkeypatch: Scoped file-dialog and user-directory replacements.
    """
    from config import settings as settings_module
    from gui.dialogs import operation_selection_dialog as module

    monkeypatch.setattr(settings_module, "user_directory", lambda: tmp_path)
    path = tmp_path / "pipeline.json"
    values = pipeline_settings(("colour", "reduce"))
    save_preset(path, "enhance", values)
    monkeypatch.setattr(module.QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    selection = OperationSelectionDialog(load_default("enhance"))
    selection.import_preset()
    assert selection.values == values
    assert selection.checkboxes["reduce"].isChecked()
    assert not selection.checkboxes["dehaze"].isChecked()
    path.write_text("{}")
    selection.import_preset()
    assert selection.values == values
    assert selection.error.text()
    selection.close()


@pytest.mark.parametrize("comparison", [False, True])
@pytest.mark.parametrize("stabilise", [False, True])
@pytest.mark.parametrize("trial", [None, TrialRange(0.25, 0.75)])
def test_pipeline_render(
    clip: Path,
    pipeline_runner: FFmpegRunner,
    comparison: bool,
    stabilise: bool,
    trial: TrialRange | None,
) -> None:
    """Render active combinations without intermediates, including stabilised comparisons.

    :param clip: One-second synthetic source with audio.
    :param pipeline_runner: Full FFmpeg build when available.
    :param comparison: Whether to stack original and processed branches.
    :param stabilise: Whether to analyse and correct motion.
    :param trial: Optional non-zero-start source interval.
    """
    enabled = STAGE_ORDER if stabilise else STAGE_ORDER[1:]
    settings = pipeline_settings(enabled) | {"comparison": comparison}
    settings["stages"]["stabilise"]["keep_motion"] = True
    if reason := pipeline_runner.unavailable("enhance", comparison, settings):
        pytest.skip(reason)
    phases = []
    intermediates = []
    run = pipeline_runner.run

    def record(
        arguments: list[str],
        work: Path,
        duration: float,
        progress: Callable[[float], None],
        log: Callable[[str], None],
    ) -> None:
        """Record actual runner calls and any unintended intermediate video files.

        :param arguments: FFmpeg command arguments.
        :param work: Private job directory.
        :param duration: Expected phase duration.
        :param progress: Phase progress callback.
        :param log: Diagnostic callback.
        """
        phases.append(list(arguments))
        run(arguments, work, duration, progress, log)
        intermediates.extend(
            path.name for path in work.iterdir() if path.suffix in (".mkv", ".mov")
        )

    pipeline_runner.run = record
    events = []
    original = clip.read_bytes()
    result = run_batch(
        [clip], "enhance", settings, pipeline_runner, lambda *args: events.append(args), trial=trial
    )[0]
    assert result.status == "completed", result.message
    assert len(phases) == (2 if stabilise else 1)
    assert sum(arguments.count("-c:v") for arguments in phases) == 1
    assert not intermediates
    metadata = pipeline_runner.probe(result.output)
    assert metadata.width == (320 if comparison else 160)
    assert metadata.height == 120 and metadata.audio
    assert metadata.duration == pytest.approx(0.5 if trial else 1, abs=0.1)
    if trial:
        for arguments in phases:
            assert "-ss" in arguments and "-t" in arguments
    assert result.output.with_suffix(".trf").exists() == stabilise
    assert clip.read_bytes() == original
    percentages = [event[1] for event in events if event[1] >= 0]
    assert percentages == sorted(percentages)
    assert percentages[-1] == 100 and all(value < 100 for value in percentages[:-1])
    assert not list(clip.parent.glob(".reefframe-*"))


@pytest.mark.parametrize("operation", STAGE_ORDER)
def test_single_stage_matches_standalone(
    clip: Path, pipeline_runner: FFmpegRunner, operation: str
) -> None:
    """Single-stage pipeline output matches standalone video with equivalent output settings.

    :param clip: Synthetic source clip.
    :param pipeline_runner: Runner supporting VidStab when available.
    :param operation: Independently usable stage to compare.
    """
    settings = pipeline_settings((operation,))
    if reason := pipeline_runner.unavailable("enhance", False, settings):
        pytest.skip(reason)
    output = clip.parent / "pipeline.mp4"
    standalone = clip.parent / "standalone.mp4"
    result = run_batch(
        [clip],
        "enhance",
        settings | {"output_name": output.name},
        pipeline_runner,
        lambda *args: None,
    )[0]
    assert result.status == "completed", result.message
    stage_settings = load_default(operation) | settings["stages"][operation]
    configuration = PipelineConfiguration.from_settings(settings)
    stage_settings.update(crf=configuration.encoding.crf, preset=configuration.encoding.preset)
    stage_settings["output_name"] = standalone.name
    result = run_batch([clip], operation, stage_settings, pipeline_runner, lambda *args: None)[0]
    assert result.status == "completed", result.message
    digests = []
    for path in (output, standalone):
        digests.append(
            subprocess.check_output(
                [
                    pipeline_runner.ffmpeg,
                    "-v",
                    "error",
                    "-i",
                    str(path),
                    "-map",
                    "0:v:0",
                    "-f",
                    "md5",
                    "-",
                ]
            )
        )
    assert digests[0] == digests[1]


@pytest.mark.parametrize("cancel_phase", [0, 1])
def test_pipeline_cancel_preserves_outputs(
    clip: Path, pipeline_runner: FFmpegRunner, cancel_phase: int
) -> None:
    """Cancellation in either stabilisation phase preserves existing published files.

    :param clip: Disposable synthetic video.
    :param pipeline_runner: FFmpeg runner with replaceable execution method.
    :param cancel_phase: Zero-based phase at which cancellation is simulated.
    """
    settings = pipeline_settings(("stabilise", "gamma")) | {"overwrite": True}
    settings["stages"]["stabilise"]["keep_motion"] = True
    destination = clip.with_name(clip.stem + "-enhanced.mp4")
    motion = destination.with_suffix(".trf")
    destination.write_bytes(b"existing video")
    motion.write_bytes(b"existing motion")
    original = clip.read_bytes()
    calls = []
    pipeline_runner.unavailable = lambda *args: ""

    def cancel(
        arguments: list[str],
        work: Path,
        duration: float,
        progress: Callable[[float], None],
        log: Callable[[str], None],
    ) -> None:
        """Write private partial data, then simulate cancellation at the requested phase.

        :param arguments: Planned phase arguments.
        :param work: Private job directory.
        :param duration: Unused expected duration.
        :param progress: Unused progress callback.
        :param log: Unused diagnostic callback.
        """
        (work / "motion.trf").write_bytes(b"private motion")
        if len(calls) == cancel_phase:
            (work / "result.mp4").write_bytes(b"partial")
            raise CancelledError("Cancelled")
        calls.append(arguments)

    pipeline_runner.run = cancel
    result = run_batch([clip], "enhance", settings, pipeline_runner, lambda *args: None)[0]
    assert result.status == "cancelled"
    assert destination.read_bytes() == b"existing video"
    assert motion.read_bytes() == b"existing motion"
    assert clip.read_bytes() == original
    assert not list(clip.parent.glob(".reefframe-*"))


def test_motion_collision_and_disabled_stage(clip: Path, pipeline_runner: FFmpegRunner) -> None:
    """Check motion collisions only when enabled and preserve existing motion files.

    :param clip: Synthetic source video.
    :param pipeline_runner: Runner for actual video rendering.
    """
    settings = pipeline_settings(("stabilise",))
    settings["stages"]["stabilise"]["keep_motion"] = True
    destination = clip.with_name(clip.stem + "-enhanced.mp4")
    motion = destination.with_suffix(".trf")
    motion.write_bytes(b"existing motion")
    pipeline_runner.unavailable = lambda *args: ""
    failed = run_batch([clip], "enhance", settings, pipeline_runner, lambda *args: None)[0]
    assert failed.status == "failed" and "Motion data already exists" in failed.message
    settings["enabled"] = ["reduce"]
    result = run_batch([clip], "enhance", settings, pipeline_runner, lambda *args: None)[0]
    assert result.status == "completed", result.message
    assert motion.read_bytes() == b"existing motion"


def test_worker_freezes_nested_settings(application: QApplication) -> None:
    """Nested widget settings cannot mutate a captured batch configuration.

    :param application: Shared QApplication for creating a worker thread object.
    """
    from gui.workers import BatchWorker

    settings = pipeline_settings()
    worker = BatchWorker([], "enhance", settings, SimpleNamespace())
    settings["stages"]["gamma"]["gamma"] = 3.0
    assert worker.settings["stages"]["gamma"]["gamma"] == 1.2


@pytest.mark.parametrize("audio_policy", ["copy", "aac", "remove"])
@pytest.mark.parametrize("clip", [False, True], indirect=True)
def test_pipeline_audio_policy(
    clip: Path, pipeline_runner: FFmpegRunner, audio_policy: str
) -> None:
    """Shared audio policy applies exactly once, including sources without audio.

    :param clip: Synthetic video with or without audio.
    :param pipeline_runner: Available FFmpeg runner.
    :param audio_policy: Requested final audio treatment.
    """
    had_audio = pipeline_runner.probe(clip).audio
    settings = pipeline_settings(("colour", "gamma")) | {"audio_policy": audio_policy}
    result = run_batch([clip], "enhance", settings, pipeline_runner, lambda *args: None)[0]
    assert result.status == "completed", result.message
    assert pipeline_runner.probe(result.output).audio == (had_audio and audio_policy != "remove")


def test_failed_pipeline_preserves_existing(clip: Path, pipeline_runner: FFmpegRunner) -> None:
    """Rendering errors leave existing video and motion outputs untouched.

    :param clip: Disposable synthetic video.
    :param pipeline_runner: Runner with replaced failing execution.
    """
    settings = pipeline_settings(("stabilise", "gamma")) | {"overwrite": True}
    settings["stages"]["stabilise"]["keep_motion"] = True
    destination = clip.with_name(clip.stem + "-enhanced.mp4")
    motion = destination.with_suffix(".trf")
    destination.write_bytes(b"existing video")
    motion.write_bytes(b"existing motion")
    original = clip.read_bytes()
    pipeline_runner.unavailable = lambda *args: ""

    def fail(*args: object) -> None:
        """Simulate failure without publishing private outputs.

        :param args: Unused runner arguments.
        """
        raise RuntimeError("Unsupported transform in filter graph")

    pipeline_runner.run = fail
    result = run_batch([clip], "enhance", settings, pipeline_runner, lambda *args: None)[0]
    assert result.status == "failed"
    assert "Unsupported transform" in result.message
    assert destination.read_bytes() == b"existing video"
    assert motion.read_bytes() == b"existing motion"
    assert clip.read_bytes() == original
    assert not list(clip.parent.glob(".reefframe-*"))


def test_change_operations_with_invalid_filename(
    application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid shared options show an inline error instead of raising from a UI callback.

    :param application: Shared Qt application.
    :param monkeypatch: Scoped selection execution replacement.
    """
    dialog = EnhanceDialog()
    dialog.controls["output_name"].setText("../invalid")
    opened = []
    monkeypatch.setattr(OperationSelectionDialog, "exec", lambda self: opened.append(self) or 0)
    dialog.change_operations()
    assert not opened
    assert "filename" in dialog.error.text()
    assert dialog.controls["output_name"].text() == "../invalid"
    dialog.close()
