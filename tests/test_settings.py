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


def test_standard_directories(monkeypatch, tmp_path):
    """Use Qt's distinct configuration and local-data locations.

    :param monkeypatch: Scoped replacement of Qt's directory lookup.
    :param tmp_path: Isolated temporary directory supplied by pytest.
    """
    from config import settings

    locations = {
        settings.QStandardPaths.StandardLocation.AppConfigLocation: str(tmp_path / "config"),
        settings.QStandardPaths.StandardLocation.AppLocalDataLocation: str(tmp_path / "data"),
    }
    monkeypatch.setattr(settings.QStandardPaths, "writableLocation", locations.__getitem__)
    assert settings.user_directory() == tmp_path / "config"
    assert settings.log_directory() == tmp_path / "data" / "logs"


def test_migrate_settings(monkeypatch, tmp_path):
    """Preserve legacy preferences and presets without replacing new settings.

    :param monkeypatch: Scoped replacement of home and destination directories.
    :param tmp_path: Isolated temporary directory supplied by pytest.
    """
    from config import settings

    monkeypatch.setattr(settings.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(settings.sys, "platform", "darwin")
    destination = tmp_path / "new-config"
    monkeypatch.setattr(settings, "user_directory", lambda: destination)
    legacy = tmp_path / "Library" / "Application Support" / "ReefFrame"
    (legacy / "presets").mkdir(parents=True)
    (legacy / "preferences.ini").write_text("old preferences")
    (legacy / "presets" / "example.json").write_text("{}")
    settings.migrate_user_settings()
    assert (destination / "preferences.ini").read_text() == "old preferences"
    assert (destination / "presets" / "example.json").read_text() == "{}"
    (destination / "preferences.ini").write_text("new preferences")
    settings.migrate_user_settings()
    assert (destination / "preferences.ini").read_text() == "new preferences"
    assert (legacy / "preferences.ini").read_text() == "old preferences"
