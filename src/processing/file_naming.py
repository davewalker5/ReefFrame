"""Eligibility and source-safe output naming."""

from pathlib import Path

SUFFIXES = {
    "convert": "",
    "dehaze": "-dehazed",
    "enhance": "-enhanced",
    "reduce": "-reduced",
    "stabilise": "-stabilised",
    "gif": "",
    "snapshot": "",
}


def eligible(path: Path, operation: str) -> bool:
    """
    Return whether a regular file matches an operation.

    :param path: Filesystem path to inspect or read.
    :param operation: Registered operation name used to select defaults and processing behaviour.
    :return: True for a regular file with the operation-specific input extension.
    """
    return path.is_file() and path.suffix.lower() == (".mov" if operation == "convert" else ".mp4")


def scan(folder: Path) -> list[Path]:
    """
    List immediate video files, case insensitively, without recursion.

    :param folder: Folder whose immediate video files will be listed.
    :return: Immediate MP4/MOV file paths sorted case-insensitively by filename.
    :raises OSError: If the folder cannot be read.
    """
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".mov", ".mp4")),
        key=lambda p: p.name.casefold(),
    )


def output_path(source: Path, operation: str, settings: dict) -> Path:
    """
    Construct a destination and reject paths that could overwrite the source.

    :param source: Path to the source video, which must remain unchanged.
    :param operation: Registered operation name used to select defaults and processing behaviour.
    :param settings: Complete operation settings; validated before use.
    :return: Destination path using the configured filename or operation suffix.
    :raises ValueError: If the filename extension is invalid or the destination resolves to the
        source.
    """
    extension = {"gif": ".gif", "snapshot": ".png"}.get(operation, ".mp4")
    suffix = SUFFIXES[operation]
    if operation == "snapshot":
        suffix = "-" + settings["timestamp"].replace(":", "-")
    if settings["comparison"]:
        suffix += "-comparison"
    destination = source.with_name(settings["output_name"] or source.stem + suffix + extension)
    if destination.suffix.lower() != extension:
        raise ValueError(f"Output must end in {extension}")
    if destination.resolve() == source.resolve():
        raise ValueError("Output must not overwrite the source")
    return destination
