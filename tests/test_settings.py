"""Preset compatibility, validation and immutable defaults."""

import json

import pytest

from config.settings import OPERATIONS, load_default, load_preset, save_preset, validate


@pytest.mark.parametrize("operation", OPERATIONS)
def test_roundtrip(operation, tmp_path):
    """
    All shipped defaults survive preset export and import unchanged.

    :param operation: Registered operation name used to select defaults and processing behaviour.
    :param tmp_path: Isolated temporary directory supplied by pytest.
    """
    default = load_default(operation)
    assert validate(operation, default) == default
    path = tmp_path / "preset.json"
    save_preset(path, operation, default)
    assert load_preset(path, operation) == default
    default["overwrite"] = True
    assert not load_default(operation)["overwrite"]


@pytest.mark.parametrize(
    "change",
    [
        {"crf": True},
        {"crf": 52},
        {"crf": -1},
        {"extra": 1},
        {"preset": "unknown"},
        {"output_name": "../source.mp4"},
    ],
)
def test_invalid(change):
    """
    Reject unknown keys, wrong types, unsafe paths and unsupported values.

    :param change: Settings changes expected to fail validation.
    """
    with pytest.raises(ValueError):
        validate("convert", load_default("convert") | change)


def test_mismatched_preset(tmp_path):
    """
    Reject mismatched operations and malformed JSON.

    :param tmp_path: Isolated temporary directory supplied by pytest.
    """
    path = tmp_path / "bad.json"
    save_preset(path, "reduce", load_default("reduce"))
    with pytest.raises(ValueError):
        load_preset(path, "convert")
    path.write_text("{")
    with pytest.raises(json.JSONDecodeError):
        load_preset(path, "convert")
