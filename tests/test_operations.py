"""Verify every operation's command construction without invoking FFmpeg."""

import importlib
from pathlib import Path

import pytest

from config.settings import OPERATIONS, load_default


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("comparison", [False, True])
def test_commands(operation, comparison):
    """
    Commands preserve explicit audio policies and comparison orientation.

    :param operation: Registered operation name used to select defaults and processing behaviour.
    :param comparison: Whether to include original-left, processed-right comparison behaviour.
    """
    module = importlib.import_module("processing." + operation)
    settings = load_default(operation) | {"comparison": comparison}
    source, destination = Path("/tmp/input file.mp4"), Path("/tmp/result.mp4")
    if operation == "stabilise":
        phases = module.build_phases(source, destination, settings)
        assert "vidstabdetect=shakiness=5:accuracy=5:result=motion.trf" in phases[0][1]
        assert len(phases) == (3 if comparison else 2)
        args = phases[-1][1]
    else:
        args = module.build_arguments(source, destination, settings)
    assert args[-1] == str(destination)
    assert str(source) in args
    if comparison:
        assert "hstack=inputs=2" in " ".join(args)
    if operation in ("convert", "stabilise"):
        assert "aac" in args and "192k" in args
    if operation in ("dehaze", "enhance", "reduce"):
        assert "copy" in args
    if operation == "enhance":
        assert (
            "eq=contrast=1.3:brightness=-0.03,eq=contrast=1.3,vibrance=intensity=0.3"
            in " ".join(args)
        )
