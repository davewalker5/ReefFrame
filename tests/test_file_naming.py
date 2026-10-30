"""File discovery and source protection."""

import pytest

from config.settings import load_default
from processing.file_naming import eligible, output_path, scan


def test_scan_and_eligibility(tmp_path):
    """
    Scanning is nonrecursive; eligible extensions remain eligible after processing.

    :param tmp_path: Isolated temporary directory supplied by pytest.
    """
    for name in ["a.MP4", "b.MoV", "c-enhanced.mp4", "ignored.txt"]:
        (tmp_path / name).touch()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub/x.mp4").touch()
    assert len(scan(tmp_path)) == 3
    assert eligible(tmp_path / "a.MP4", "reduce")
    assert eligible(tmp_path / "b.MoV", "convert")
    assert eligible(tmp_path / "c-enhanced.mp4", "enhance")


def test_source_protection(tmp_path):
    """
    Even explicit overwrite settings cannot target the source.

    :param tmp_path: Isolated temporary directory supplied by pytest.
    """
    path = tmp_path / "reef.mp4"
    with pytest.raises(ValueError, match="source"):
        output_path(
            path, "reduce", load_default("reduce") | {"output_name": path.name, "overwrite": True}
        )
    assert output_path(path, "snapshot", load_default("snapshot")).name == "reef-00-00-00.png"


@pytest.mark.parametrize(
    "suffix", ["enhanced", "dehazed", "reduced", "stabilised", "enhanced-comparison"]
)
@pytest.mark.parametrize(
    "operation", ["dehaze", "enhance", "reduce", "gif", "snapshot", "stabilise"]
)
def test_reprocess_outputs(tmp_path, suffix, operation):
    """
    An existing output remains selectable for every MP4 operation.

    :param tmp_path: Isolated temporary directory supplied by pytest.
    :param suffix: Previously processed filename suffix that must not prevent eligibility.
    :param operation: Registered operation name used to select defaults and processing behaviour.
    """
    source = tmp_path / f"GOPR0585-001-{suffix}.mp4"
    source.touch()
    assert eligible(source, operation)
    assert not eligible(source, "convert")
    destination = output_path(source, operation, load_default(operation))
    assert destination != source
