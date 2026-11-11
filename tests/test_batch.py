"""Real generated-media coverage for all operations and comparison modes."""

import shutil
from threading import Event
from types import SimpleNamespace

import pytest

from config.settings import OPERATIONS, load_default, load_preset
from processing.batch import PRESET_OPERATIONS, run_batch
from processing.ffmpeg_runner import FFmpegRunner
from processing.file_naming import output_path
from processing.trial import TrialRange


@pytest.mark.parametrize("operation", sorted(PRESET_OPERATIONS))
@pytest.mark.parametrize("trial", [None, TrialRange(0, 0.5)])
@pytest.mark.parametrize("overwrite", [False, True])
def test_per_output_preset(tmp_path, operation, trial, overwrite):
    """Save importable settings beside custom outputs, including trial outputs.

    :param tmp_path: Isolated output directory.
    :param operation: Correction operation under test.
    :param trial: Optional trial interval.
    :param overwrite: Whether existing output and preset files should be replaced.
    """
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    settings = load_default(operation) | {"output_name": "custom.mp4", "overwrite": overwrite}
    destination = output_path(source, operation, settings)
    if trial is not None:
        destination = destination.with_stem(destination.stem + trial.suffix())
    if overwrite:
        destination.write_bytes(b"previous output")
        destination.with_suffix(".json").write_text("previous preset")

    def render(arguments, work, *args):
        """Create simulated render and motion outputs for each processing phase.

        :param arguments: FFmpeg arguments, ending with the output path.
        :param work: Temporary work directory.
        :param args: Unused progress and logging arguments.
        """
        if arguments[-1] != "-":
            (work / arguments[-1]).write_bytes(b"rendered")
        (work / "motion.trf").write_bytes(b"motion")

    runner = SimpleNamespace(
        cancelled=Event(),
        unavailable=lambda *args: None,
        probe=lambda path: SimpleNamespace(duration=1),
        run=render,
    )
    result = run_batch([source], operation, settings, runner, lambda *args: None, trial=trial)[0]
    assert result.status == "completed", result.message
    preset = result.output.with_suffix(".json")
    assert load_preset(preset, operation) == settings


def test_existing_preset_is_preserved(tmp_path):
    """An existing sidecar blocks rendering unless overwrite is enabled.

    :param tmp_path: Isolated output directory.
    """
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    settings = load_default("gamma")
    destination = output_path(source, "gamma", settings)
    preset = destination.with_suffix(".json")
    preset.write_text("existing preset")
    runner = SimpleNamespace(cancelled=Event())
    result = run_batch([source], "gamma", settings, runner, lambda *args: None)[0]
    assert result.status == "failed"
    assert "Preset already exists" in result.message
    assert preset.read_text() == "existing preset"
    assert not destination.exists()


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("comparison", [False, True])
@pytest.mark.parametrize("clip", [False, True], indirect=True)
def test_integration(clip, operation, comparison):
    """
    Process silent/audio clips safely, then skip existing outputs.

    :param clip: Disposable synthetic source clip supplied by the media fixture.
    :param operation: Registered operation name used to select defaults and processing behaviour.
    :param comparison: Whether to include original-left, processed-right comparison behaviour.
    """
    runner = FFmpegRunner()
    settings = load_default(operation) | {"comparison": comparison}
    if reason := runner.unavailable(
        operation, comparison, settings if operation == "enhance" else None
    ):
        pytest.skip(reason)
    if operation == "convert":
        source = clip.with_suffix(".MOV")
        shutil.copyfile(clip, source)
        clip.unlink()
    else:
        source = clip
    settings = load_default(operation) | {"comparison": comparison}
    events = []
    result = run_batch([source], operation, settings, runner, lambda *args: events.append(args))
    assert result[0].status == "completed", result[0].message
    progress_events = [event for event in events if event[1] >= 0]
    assert progress_events[-1] == (source.name, 100, "Completed")
    output = result[0].output
    assert output.stat().st_size > 0
    preset = output.with_suffix(".json")
    if operation in PRESET_OPERATIONS:
        assert load_preset(preset, operation) == settings
    else:
        assert not preset.exists()
    metadata = runner.probe(output)
    if operation not in ("gif", "snapshot"):
        assert metadata.audio == runner.probe(source).audio
    if comparison:
        expected = 960 if operation == "gif" else 320
        assert metadata.width == expected
    assert (
        run_batch([source], operation, settings, runner, lambda *args: None)[0].status == "skipped"
    )
    assert source.exists()
    assert not list(source.parent.glob(".reefframe-*"))


def test_failed_output_preserves_existing(clip):
    """
    A failed overwrite leaves the prior output and source intact.

    :param clip: Disposable synthetic source clip supplied by the media fixture.
    """
    runner = FFmpegRunner()
    destination = clip.with_name(clip.stem + "-reduced.mp4")
    destination.write_bytes(b"existing")
    original = clip.read_bytes()

    def fail(*args):
        """
        Simulate an encoder failure after job setup.

        :param args: Unused runner arguments accepted by the simulated failure callback.
        """
        raise RuntimeError("Encoder failed")

    runner.run = fail
    result = run_batch(
        [clip], "reduce", load_default("reduce") | {"overwrite": True}, runner, lambda *args: None
    )
    assert result[0].status == "failed"
    assert destination.read_bytes() == b"existing"
    assert clip.read_bytes() == original
    assert not list(clip.parent.glob(".reefframe-*"))


def test_cancelled_queue_never_starts(clip):
    """
    A cancelled queue produces no destinations and leaves source untouched.

    :param clip: Disposable synthetic source clip supplied by the media fixture.
    """
    runner = FFmpegRunner()
    runner.cancel()
    assert run_batch([clip], "reduce", load_default("reduce"), runner, lambda *args: None) == []
    assert not clip.with_name(clip.stem + "-reduced.mp4").exists()


def test_overwrite_success_and_motion_cleanup(clip):
    """
    Explicit overwrite replaces a destination only after a verified encode.

    :param clip: Disposable synthetic source clip supplied by the media fixture.
    """
    runner = FFmpegRunner()
    settings = load_default("reduce") | {"overwrite": True}
    destination = clip.with_name(clip.stem + "-reduced.mp4")
    destination.write_bytes(b"previous output")
    results = run_batch([clip], "reduce", settings, runner, lambda *args: None)
    assert results[0].status == "completed"
    assert runner.probe(destination).width == 160
    assert not list(clip.parent.glob(".reefframe-*"))


def test_queued_sources_protected(clip):
    """
    A user-specified output may not target another queued input.

    :param clip: Disposable synthetic source clip supplied by the media fixture.
    """
    other = clip.with_name("other.mp4")
    other.write_bytes(clip.read_bytes())
    original = other.read_bytes()
    results = run_batch(
        [clip, other],
        "reduce",
        load_default("reduce") | {"overwrite": True, "output_name": other.name},
        FFmpegRunner(),
        lambda *args: None,
    )
    assert all(result.status == "failed" for result in results)
    assert other.read_bytes() == original


@pytest.mark.parametrize("size", ["2704x1520", "720x1280"])
def test_comparison_resolution_and_frame_timing(tmp_path, size):
    """
    High-resolution and portrait comparisons remain HD-sized with continuous cadence.

    :param tmp_path: Isolated temporary directory supplied by pytest.
    :param size: Synthetic video dimensions expressed as widthxheight.
    """
    import json
    import subprocess
    from fractions import Fraction

    runner = FFmpegRunner()
    source = tmp_path / "camera.mp4"
    subprocess.run(
        [
            runner.ffmpeg,
            "-v",
            "error",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size}:rate=24000/1001:duration=1.001",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(source),
        ],
        check=True,
    )
    result = run_batch(
        [source],
        "dehaze",
        load_default("dehaze") | {"comparison": True},
        runner,
        lambda *args: None,
    )[0]
    assert result.status == "completed", result.message
    document = json.loads(
        subprocess.check_output(
            [
                runner.ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_streams",
                "-show_packets",
                "-show_entries",
                "stream=width,height,avg_frame_rate:packet=pts_time",
                "-of",
                "json",
                str(result.output),
            ],
            text=True,
        )
    )
    stream = document["streams"][0]
    assert stream["width"] <= 1920
    assert stream["height"] <= 1080
    assert stream["width"] % 2 == stream["height"] % 2 == 0
    assert Fraction(stream["avg_frame_rate"]) == Fraction(24000, 1001)
    timestamps = sorted(float(packet["pts_time"]) for packet in document["packets"])
    assert len(timestamps) == 24
    assert all(
        b - a == pytest.approx(1001 / 24000, abs=0.000002)
        for a, b in zip(timestamps, timestamps[1:])
    )
