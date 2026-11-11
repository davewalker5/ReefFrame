"""Validated version-two pipeline configuration and typed execution settings."""

from copy import deepcopy
from dataclasses import dataclass

from config.settings import load_default, validate

STAGE_ORDER = ("stabilise", "dehaze", "colour", "gamma", "contrast", "reduce")
STAGE_FIELDS = {
    "stabilise": ("shakiness", "accuracy", "smoothing", "optzoom", "keep_motion"),
    "dehaze": ("contrast", "brightness"),
    "colour": ("red_gain", "green_gain", "blue_gain"),
    "gamma": ("gamma", "shadow_lift", "shadow_range"),
    "contrast": ("contrast",),
    "reduce": (),
}


@dataclass(frozen=True)
class EncodingSettings:
    """The single effective final video encoding policy."""

    crf: int
    preset: str


@dataclass(frozen=True)
class PipelineStage:
    """An enabled stage with its independently validated operation parameters."""

    operation: str
    parameters: dict[str, int | float | bool]


@dataclass(frozen=True)
class PipelineConfiguration:
    """A detached, ordered execution snapshot with shared output settings."""

    stages: tuple[PipelineStage, ...]
    encoding: EncodingSettings
    comparison: bool
    audio_policy: str
    output_name: str
    overwrite: bool

    @classmethod
    def from_settings(cls, settings: dict) -> PipelineConfiguration:
        """Validate and freeze the stage order and effective encoding policy.

        :param settings: Complete nested pipeline settings.
        :return: Detached pipeline execution configuration.
        :raises ValueError: If settings are invalid.
        """
        values = validate_pipeline(settings)
        reduced = "reduce" in values["enabled"]
        return cls(
            stages=tuple(PipelineStage(name, values["stages"][name]) for name in values["enabled"]),
            encoding=EncodingSettings(
                values["reduction_crf"] if reduced else values["crf"],
                values["reduction_preset"] if reduced else values["preset"],
            ),
            comparison=values["comparison"],
            audio_policy=values["audio_policy"],
            output_name=values["output_name"],
            overwrite=values["overwrite"],
        )

    def output_settings(self) -> dict:
        """Expose shared settings in the existing command builder's format.

        :return: Effective encoder and audio settings for the final render.
        """
        return {
            "crf": self.encoding.crf,
            "preset": self.encoding.preset,
            "comparison": self.comparison,
            "audio_policy": self.audio_policy,
        }

    def keeps_motion(self) -> bool:
        """Check motion publication only for an enabled stabilisation stage.

        :return: Whether motion data should be retained.
        """
        return any(
            stage.operation == "stabilise" and stage.parameters["keep_motion"]
            for stage in self.stages
        )


def validate_pipeline(settings: dict) -> dict:
    """Validate the entire version-two schema without modifying caller data.

    :param settings: Complete pipeline settings, including disabled-stage values.
    :return: Deep copy with enabled stages normalised to processing order.
    :raises ValueError: If keys, stage selection or parameter values are invalid.
    """
    expected = load_default("enhance")
    if not isinstance(settings, dict) or settings.keys() != expected.keys():
        raise ValueError("Pipeline settings must contain exactly the documented keys")
    enabled = settings["enabled"]
    if (
        not isinstance(enabled, list)
        or not enabled
        or any(type(name) is not str or name not in STAGE_ORDER for name in enabled)
        or len(set(enabled)) != len(enabled)
    ):
        raise ValueError("Choose at least one operation, without unknown or duplicate stages")
    stages = settings["stages"]
    if not isinstance(stages, dict) or set(stages) != set(STAGE_ORDER):
        raise ValueError("Pipeline stages must contain exactly the six documented operations")
    for operation, fields in STAGE_FIELDS.items():
        parameters = stages[operation]
        if not isinstance(parameters, dict) or set(parameters) != set(fields):
            raise ValueError(f"Invalid parameter keys for {operation}")
        validate(operation, load_default(operation) | parameters)
    # Existing standalone validation supplies numeric, enum and filename rules.
    shared = {key: settings[key] for key in load_default("reduce")}
    validate("reduce", shared)
    validate(
        "reduce",
        shared | {"crf": settings["reduction_crf"], "preset": settings["reduction_preset"]},
    )
    result = deepcopy(settings)
    result["enabled"] = [name for name in STAGE_ORDER if name in enabled]
    return result
