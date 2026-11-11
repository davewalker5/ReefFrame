"""File discovery and source protection."""

import pytest

from config.settings import OPERATIONS, load_default
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


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("name", ["custom", "custom.v2", "custom.MP4", "custom.mp4"])
def test_manual_output_extension(tmp_path, operation, name):
    """Append the correct extension without replacing user text or duplicating suffixes.

    :param tmp_path: Isolated test folder.
    :param operation: Registered processing operation.
    :param name: Manually entered filename.
    """
    extension = {"gif": ".gif", "snapshot": ".png"}.get(operation, ".mp4")
    expected = name if name.lower().endswith(extension) else name + extension
    settings = load_default(operation) | {"output_name": name}
    assert output_path(tmp_path / "source.mp4", operation, settings).name == expected


@pytest.mark.parametrize("operation,extension", [("gif", ".gif"), ("snapshot", ".png")])
def test_existing_image_extension(tmp_path, operation, extension):
    """Preserve matching image output extensions regardless of case.

    :param tmp_path: Isolated test folder.
    :param operation: Image-producing operation.
    :param extension: Expected image file suffix.
    """
    name = "custom" + extension.upper()
    settings = load_default(operation) | {"output_name": name}
    assert output_path(tmp_path / "source.mp4", operation, settings).name == name


def test_extension_completion_preserves_source_protection(tmp_path):
    """Reject a manual stem that becomes the source path after extension completion.

    :param tmp_path: Isolated test folder.
    """
    settings = load_default("gamma") | {"output_name": "source", "overwrite": True}
    with pytest.raises(ValueError, match="source"):
        output_path(tmp_path / "source.mp4", "gamma", settings)
