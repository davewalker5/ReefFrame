"""Validated last-confirmed dialog settings in the existing Qt user preferences file."""

import json
import logging

from PySide6.QtCore import QSettings

from config import settings as operation_settings

LOGGER = logging.getLogger(__name__)
PER_RUN_KEYS = ("output_name", "overwrite")


def user_preferences() -> QSettings:
    """Open the existing INI preferences in Qt's application configuration directory.

    :return: Fresh settings handle sharing the application's preferences.ini file.
    """
    return QSettings(
        str(operation_settings.user_directory() / "preferences.ini"), QSettings.Format.IniFormat
    )


def load_operation_settings(operation: str) -> dict:
    """Restore last-confirmed parameters, falling back to defaults on incompatible data.

    :param operation: Registered standalone operation or enhancement pipeline identifier.
    :return: Fresh validated settings with per-run output controls reset.
    """
    defaults = operation_settings.load_default(operation)
    preferences = user_preferences()
    stored = preferences.value(f"operations/{operation}")
    if stored is None:
        return defaults
    try:
        document = json.loads(stored)
        version = 2 if operation == "enhance" else 1
        if (
            not isinstance(document, dict)
            or set(document) != {"version", "settings"}
            or type(document["version"]) is not int
            or document["version"] != version
        ):
            raise ValueError("Unsupported remembered settings format")
        values = operation_settings.validate(operation, document["settings"])
    except (TypeError, ValueError) as error:
        LOGGER.warning("Ignoring invalid remembered %s settings: %s", operation, error)
        return defaults
    for key in PER_RUN_KEYS:
        values[key] = defaults[key]
    return values


def remember_operation_settings(operation: str, values: dict) -> None:
    """Persist validated processing parameters without retaining per-run output controls.

    :param operation: Registered standalone operation or enhancement pipeline identifier.
    :param values: Complete validated dialog settings, including disabled pipeline stages.
    :raises ValueError: If any supplied settings are invalid.
    :raises OSError: If user preferences cannot be written.
    """
    values = operation_settings.validate(operation, values)
    defaults = operation_settings.load_default(operation)
    for key in PER_RUN_KEYS:
        values[key] = defaults[key]
    document = {"version": 2 if operation == "enhance" else 1, "settings": values}
    preferences = user_preferences()
    preferences.setValue(f"operations/{operation}", json.dumps(document))
    preferences.sync()
    if preferences.status() != QSettings.Status.NoError:
        raise OSError(
            "Cannot save processing preferences. Check the user settings folder is writable."
        )


def remember_pipeline_selection(enabled: list[str]) -> None:
    """Remember confirmed stage selection while preserving last-confirmed parameter values.

    :param enabled: Non-empty pipeline stage selection in any order.
    :raises ValueError: If selection contains unknown, duplicate or no stages.
    :raises OSError: If user preferences cannot be written.
    """
    values = load_operation_settings("enhance")
    values["enabled"] = enabled
    remember_operation_settings("enhance", values)
