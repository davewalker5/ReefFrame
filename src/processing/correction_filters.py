"""Shared deterministic correction filters used by standalone and pipeline renders."""

LUMA_BLACK = 16
LUMA_INTERVAL = 219


def dehaze_filter(settings: dict) -> str:
    """Build the existing initial contrast and brightness adjustment.

    :param settings: Validated dehaze parameters.
    :return: FFmpeg EQ filter expression.
    """
    return f"eq=contrast={settings['contrast']}:brightness={settings['brightness']}"


def contrast_filter(settings: dict) -> str:
    """Build contrast alone, bypassing neutral correction.

    :param settings: Validated contrast parameters.
    :return: FFmpeg filter chain.
    """
    return f"eq=contrast={settings['contrast']}" if settings["contrast"] != 1 else "null"


def colour_filter(settings: dict) -> str:
    """Build diagonal RGB gains without introducing other corrections.

    :param settings: Validated RGB gain parameters.
    :return: FFmpeg filter chain, or null for neutral gains.
    """
    if all(settings[key] == 1 for key in ("red_gain", "green_gain", "blue_gain")):
        return "null"
    return (
        f"colorchannelmixer=rr={settings['red_gain']}:"
        f"gg={settings['green_gain']}:bb={settings['blue_gain']}"
    )


def gamma_filter(settings: dict) -> str:
    """Build luma gamma followed by a smooth, limited-range shadow lift.

    :param settings: Validated gamma and shadow parameters.
    :return: FFmpeg filter chain, or null for neutral controls.
    """
    filters = []
    if settings["gamma"] != 1:
        filters.append(f"eq=gamma={settings['gamma']}")
    if settings["shadow_lift"]:
        # Bound the lift derivative to keep legal luma monotonic. The squared
        # taper reaches zero with a continuous first derivative at its boundary.
        extent = LUMA_INTERVAL * settings["shadow_range"]
        lift = settings["shadow_lift"] * extent
        filters.append(
            "scale=in_range=auto:out_range=tv,format=yuv444p,"
            f"lutyuv=y='val+{lift}*pow(clip(1-(val-{LUMA_BLACK})/{extent},0,1),2)'"
        )
    return ",".join(filters) or "null"


def motion_detection_filter(settings: dict) -> str:
    """Build motion analysis targeting the private job directory.

    :param settings: Validated stabilisation parameters.
    :return: VidStab detection filter.
    """
    return (
        f"vidstabdetect=shakiness={settings['shakiness']}:"
        f"accuracy={settings['accuracy']}:result=motion.trf"
    )


def stabilise_filter(settings: dict) -> str:
    """Build the existing geometric transform using private motion data.

    :param settings: Validated stabilisation parameters.
    :return: VidStab transformation filter.
    """
    return (
        f"vidstabtransform=input=motion.trf:smoothing={settings['smoothing']}:"
        f"optzoom={settings['optzoom']}"
    )
