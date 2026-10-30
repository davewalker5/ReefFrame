"""Shared encoding and comparison primitives; operation filters live in their modules."""

from pathlib import Path

# Side-by-side full-resolution GoPro footage can exceed common hardware decoder limits.
COMPARISON_SCALE = (
    "scale=w='min(1920,iw)':h='min(1080,ih)':"
    "force_original_aspect_ratio=decrease:force_divisible_by=2"
)


def video_arguments(settings: dict) -> list[str]:
    """
    Return explicit video encoding arguments for MP4 output.

    :param settings: Complete operation settings; validated before use.
    :return: MP4 video encoder, quality, pixel format and faststart options.
    """
    return [
        "-c:v",
        settings.get("codec", "libx264"),
        "-crf",
        str(settings["crf"]),
        "-preset",
        settings["preset"],
        "-pix_fmt",
        settings.get("pixel_format", "yuv420p"),
        "-movflags",
        "+faststart",
    ]


def audio_arguments(settings: dict, transcode: bool = False) -> list[str]:
    """
    Preserve audio unless removal or AAC encoding was explicitly selected.

    :param settings: Complete operation settings; validated before use.
    :param transcode: Whether AAC encoding is the default audio policy instead of stream copy.
    :return: Explicit mapping and audio copy, AAC encoding or removal options.
    """
    policy = settings.get("audio_policy", "aac" if transcode else "copy")
    if policy == "remove":
        return ["-an"]
    return ["-map", "0:a?", "-c:a", policy] + (
        ["-b:a", settings.get("audio_bitrate", "192k")] if policy == "aac" else []
    )


def filtered_video(
    source: Path, destination: Path, settings: dict, filters: str, transcode: bool = False
) -> list[str]:
    """
    Construct a filtered render, optionally stacking original on the left.

    :param source: Path to the source video, which must remain unchanged.
    :param destination: Path at which the generated output will be written or published.
    :param settings: Complete operation settings; validated before use.
    :param filters: FFmpeg filter chain applied to the processed video.
    :param transcode: Whether AAC encoding is the default audio policy instead of stream copy.
    :return: Complete filtered MP4 render arguments, excluding runner-wide options.
    """
    arguments = ["-i", str(source)]
    if settings["comparison"]:
        graph = (
            f"[0:v:0]split[left][work];[work]{filters}[right];"
            f"[left][right]hstack=inputs=2:shortest=1,{COMPARISON_SCALE}[v]"
        )
        arguments += ["-filter_complex", graph, "-map", "[v]"]
    else:
        arguments += ["-map", "0:v:0", "-vf", filters]
    return (
        arguments
        + video_arguments(settings)
        + audio_arguments(settings, transcode)
        + [str(destination)]
    )
