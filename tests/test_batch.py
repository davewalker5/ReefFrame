"""Real generated-media coverage for all operations and comparison modes."""

import shutil

import pytest

from config.settings import OPERATIONS, load_default
from processing.batch import run_batch
from processing.ffmpeg_runner import FFmpegRunner


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
    if runner.unavailable(operation, comparison):
        pytest.skip(runner.unavailable(operation, comparison))
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
