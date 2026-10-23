"""Application editor v2: bounded generated-media allowance.

Derived from the frozen app/media.py probe and replace_segment implementation.
Input gates remain unchanged. Only internally generated lossless masters/variants
receive the larger allowance; the prospective media/pilot implementation stays
intact. See docs/media_edit_v2.md.
"""
import hashlib
import math
from pathlib import Path
import re
import tempfile

from . import media

MediaError = media.MediaError
FPS = media.FPS
MAX_DURATION = media.MAX_DURATION
MAX_GENERATED_BYTES = 512 * 1024 * 1024
GENERATED_LIMIT_MARGIN = 2 * 1024 * 1024
_run = media._run
_input = media._input
_frame_hashes = media._frame_hashes
_verify_timing = media._verify_timing


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _generated_path(path):
    path = Path(path)
    # FFmpeg may stop successfully at -fs before all source frames are encoded.
    # Reject a margin below the cap, not merely outputs exceeding it.
    if (not path.is_file() or path.is_symlink()
            or not 12 <= path.stat().st_size < MAX_GENERATED_BYTES - GENERATED_LIMIT_MARGIN):
        raise MediaError('Generated video approached its 512 MiB limit; output rejected. Use a shorter or lower-resolution source.')
    with path.open('rb') as handle:
        if handle.read(12)[4:8] != b'ftyp':
            raise MediaError('Generated output is not an MP4 container.')
    return path


def probe_generated(path: Path) -> dict:
    """Inspect metadata without a decode output, enforce bounds, then decode one frame."""
    path = _generated_path(path)
    result = _run(
        [
            *_input(path),
            "-map",
            "0:v:0",
            "-c:v",
            "copy",
            "-frames:v",
            "0",
            "-an",
            "-f",
            "null",
            "-",
        ],
        timeout=20,
    )
    log = result.stderr.decode("utf8", errors="replace")
    duration = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", log)
    video = next(
        (line for line in log.splitlines() if "Stream #" in line and "Video:" in line),
        "",
    )
    size = re.search(r"\b(\d{2,5})x(\d{2,5})\b", video)
    rate = re.search(r"\b([\d.]+) fps", video)
    if not duration or not size or not rate:
        raise MediaError("Video duration, dimensions or frame rate are unavailable.")
    seconds = int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3])
    width, height = map(int, size.groups())
    fps = float(rate[1])
    if not 0 < seconds <= MAX_DURATION or not 1 <= fps <= 60:
        raise MediaError("Use a video up to 120 seconds and between 1 and 60 fps.")
    if (
        width * height > 1920 * 1080
        or max(width, height) > 1920
        or min(width, height) < 16
    ):
        raise MediaError("Maximum supported image size is 1920×1080 or 1080×1920.")
    if re.search(r"displaymatrix:.*rotation of (?!-?0\.00)", log):
        raise MediaError(
            "Rotated display metadata is unsupported; export an upright MP4 first."
        )
    _run(
        [*_input(path), "-map", "0:v:0", "-frames:v", "1", "-an", "-f", "null", "-"],
        timeout=20,
    )
    return {
        "duration": seconds,
        "width": width,
        "height": height,
        "fps": fps,
        "has_audio": any(
            "Stream #" in line and "Audio:" in line for line in log.splitlines()
        ),
    }


def replace_segment(
    source: Path, replacement: Path, start: float, end: float, out: Path
) -> dict:
    """Replace a frame-aligned visual interval, preserving the original audio.

    Editing works on a 24 fps yuv420p normalized master. Unchanged decoded frames
    are compared against that master before the output is published atomically.
    This is content preservation after normalization, not a bitstream-copy claim.
    """
    original, alternate = media.probe(source), media.probe(replacement)
    if not all(
        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
        for x in (start, end)
    ):
        raise MediaError("Edit boundaries must be finite seconds.")
    if (
        not 0 <= start < end <= original["duration"]
        or end - start > alternate["duration"] + 0.001
    ):
        raise MediaError(
            "The interval must fit the source and the replacement must cover its full duration."
        )
    first, stop = round(start * FPS), round(end * FPS)
    if abs(first / FPS - start) > 0.00001 or abs(stop / FPS - end) > 0.00001:
        raise MediaError(
            "Edit boundaries must align to the 24 fps timeline (multiples of 1/24 second)."
        )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() or out.resolve() in {
        Path(source).resolve(),
        Path(replacement).resolve(),
    }:
        raise MediaError("The output must be a new file.")
    width, height = original["width"] // 2 * 2, original["height"] // 2 * 2
    with tempfile.TemporaryDirectory(dir=out.parent, prefix=".edit-") as directory:
        master = Path(directory) / "master.mp4"
        generated = Path(directory) / "edited.mp4"
        _run(
            [
                *_input(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-vf",
                f"fps={FPS},scale={width}:{height},setsar=1",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                "-fs",
                str(MAX_GENERATED_BYTES),
                "-y",
                str(master),
            ]
        )
        master_meta = probe_generated(master)
        if abs(master_meta["duration"] - original["duration"]) > 1 / FPS + 0.011:
            raise MediaError("Normalized master duration changed; output rejected.")
        hashes_before = _frame_hashes(master)
        if stop > len(hashes_before):
            raise MediaError("Edit interval exceeds the decoded video frames.")
        parts, filters = [], []
        if first:
            filters.append(f"[0:v]trim=end_frame={first},setpts=PTS-STARTPTS[prefix]")
            parts.append("[prefix]")
        filters.append(
            f"[1:v]fps={FPS},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p,trim=end_frame={stop-first},setpts=PTS-STARTPTS[insert]"
        )
        parts.append("[insert]")
        if stop < len(hashes_before):
            filters.append(f"[0:v]trim=start_frame={stop},setpts=PTS-STARTPTS[suffix]")
            parts.append("[suffix]")
        filters.append("".join(parts) + f"concat=n={len(parts)}:v=1:a=0[video]")
        _run(
            [
                *_input(master),
                *_input(replacement),
                "-filter_complex_threads",
                "1",
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[video]",
                "-map",
                "0:a:0?",
                "-r:v",
                str(FPS),
                "-fps_mode:v",
                "cfr",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                "-fs",
                str(MAX_GENERATED_BYTES),
                "-y",
                str(generated),
            ]
        )
        result_meta = probe_generated(generated)
        hashes_after = _frame_hashes(generated)
        if len(hashes_before) != len(hashes_after):
            raise MediaError("The edit changed the frame count; output rejected.")
        verified = sum(
            1
            for i, digest in enumerate(hashes_before)
            if not first <= i < stop and digest == hashes_after[i]
        )
        if verified != len(hashes_before) - (stop - first):
            raise MediaError("Frames outside the replacement changed; output rejected.")
        timing = _verify_timing(generated, len(hashes_before))
        generated.replace(out)
    return {
        "editor_version": "generated-media-v2",
        "generated_limit_bytes": MAX_GENERATED_BYTES,
        "start": start,
        "end": end,
        "start_frame": first,
        "end_frame": stop,
        "fps": FPS,
        "timing": timing,
        "replaced_frames": stop - first,
        "total_frames": len(hashes_after),
        "unchanged_frames_verified": verified,
        "verification": "Decoded yuv420p frame SHA-256 outside the interval matches the 24 fps normalized master.",
        "audio": (
            "Original audio stream copied; replacement audio ignored."
            if original["has_audio"]
            else "Source is silent; replacement audio ignored."
        ),
        "normalization": f"24 fps, {width}×{height}, yuv420p; lossless H.264 encoding. Original compressed bytes are not preserved.",
        "source_sha256": _sha(source),
        "replacement_sha256": _sha(replacement),
        "output_sha256": _sha(out),
        "metadata": result_meta,
    }

