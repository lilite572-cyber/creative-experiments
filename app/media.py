"""Bounded local MP4 processing with FFmpeg. No shell, URLs or user filters."""

from __future__ import annotations

import hashlib
import math
from fractions import Fraction
import re
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw

MAX_BYTES = 100 * 1024 * 1024
MAX_DURATION = 120.0
FPS = 24


class MediaError(ValueError):
    pass


def _run(arguments: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess:
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-nostdin",
        "-v",
        "info",
        "-max_alloc",
        "67108864",
        "-threads",
        "2",
        *map(str, arguments),
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise MediaError(
            "Video processing timed out or FFmpeg is unavailable."
        ) from exc
    if completed.returncode:
        # Do not expose filesystem paths, submitted file content or command text.
        raise MediaError("FFmpeg could not decode or process this MP4 file.")
    return completed


def _input(path: Path) -> list[str]:
    return [
        "-protocol_whitelist",
        "file,pipe",
        "-f",
        "mov",
        "-i",
        str(Path(path).resolve()),
    ]


def _path(path: Path) -> Path:
    path = Path(path)
    if (
        not path.is_file()
        or path.stat().st_size > MAX_BYTES
        or path.stat().st_size < 12
    ):
        raise MediaError("A nonempty MP4 file of at most 100 MiB is required.")
    with path.open("rb") as handle:
        header = handle.read(12)
    if header[4:8] != b"ftyp":
        raise MediaError("Only MP4 containers with an ftyp header are supported.")
    return path


def probe(path: Path) -> dict:
    """Inspect metadata without a decode output, enforce bounds, then decode one frame."""
    path = _path(path)
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


def extract_frames(path: Path, out_dir: Path) -> list[dict]:
    """Return eight uniformly spaced, timestamped visual observations."""
    metadata = probe(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    # Include the opening frame and sample only valid source-frame timestamps.
    last = max(0, math.floor(metadata["duration"] * metadata["fps"]) - 1)
    indices = sorted({round(last * i / 7) for i in range(8)})
    for index in indices:
        timestamp = index / metadata["fps"]
        output = out_dir / f"frame-{index:06d}.jpg"
        _run(
            [
                *_input(path),
                "-ss",
                f"{timestamp:.9f}",
                "-frames:v",
                "1",
                "-an",
                "-vf",
                "scale=512:512:force_original_aspect_ratio=decrease",
                "-q:v",
                "3",
                "-y",
                str(output),
            ],
            timeout=20,
        )
        if not output.is_file():
            raise MediaError("A requested video frame could not be decoded.")
        frames.append({"path": output, "time": timestamp, "index": index})
    return frames


def _frame_hashes(path: Path) -> list[str]:
    result = _run(
        [
            *_input(path),
            "-map",
            "0:v:0",
            "-an",
            "-pix_fmt",
            "yuv420p",
            "-f",
            "framehash",
            "-hash",
            "sha256",
            "-",
        ]
    )
    return [
        line.split(",")[-1].strip()
        for line in result.stdout.decode().splitlines()
        if line and not line.startswith("#")
    ]


def _verify_timing(path: Path, expected_frames: int) -> dict:
    """Check encoded packet timestamps/durations exactly, without rounded log times."""
    result = _run(
        [*_input(path), "-map", "0:v:0", "-an", "-c:v", "copy", "-f", "framehash", "-"]
    )
    lines = result.stdout.decode().splitlines()
    timebase_line = next((line for line in lines if line.startswith("#tb 0:")), None)
    if timebase_line is None:
        raise MediaError("Output video timebase is unavailable; output rejected.")
    try:
        timebase = Fraction(timebase_line.split(":", 1)[1].strip())
        packets = [
            line.split(",") for line in lines if line and not line.startswith("#")
        ]
        if len(packets) != expected_frames:
            raise ValueError("Packet count differs from frame count")
        for index, packet in enumerate(packets):
            pts, duration = int(packet[2]), int(packet[3])
            if pts * timebase != Fraction(
                index, FPS
            ) or duration * timebase != Fraction(1, FPS):
                raise ValueError("Non-CFR timestamps or packet duration")
    except (ValueError, IndexError, ZeroDivisionError) as exc:
        raise MediaError(
            "Output video timestamps or frame durations changed; output rejected."
        ) from exc
    return {
        "verified": True,
        "frame_count": expected_frames,
        "frame_duration_seconds": 1 / FPS,
        "video_duration_seconds": expected_frames / FPS,
        "timebase": str(timebase),
    }


def replace_segment(
    source: Path, replacement: Path, start: float, end: float, out: Path
) -> dict:
    """Replace a frame-aligned visual interval, preserving the original audio.

    Editing works on a 24 fps yuv420p normalized master. Unchanged decoded frames
    are compared against that master before the output is published atomically.
    This is content preservation after normalization, not a bitstream-copy claim.
    """
    original, alternate = probe(source), probe(replacement)
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
                "-y",
                str(master),
            ]
        )
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
                "-y",
                str(generated),
            ]
        )
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
        result_meta = probe(generated)
        generated.replace(out)
    return {
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
        "source_sha256": hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        "replacement_sha256": hashlib.sha256(
            Path(replacement).read_bytes()
        ).hexdigest(),
        "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "metadata": result_meta,
    }


def make_demo(path: Path, hook: str = "packaging", duration: float = 8) -> None:
    """Author a clearly synthetic, silent coffee clip. No generative API."""
    if hook not in {"packaging", "preparation"} or not 1 <= duration <= 30:
        raise MediaError("Invalid demo settings.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="creative-demo-") as directory:
        root = Path(directory)
        for i in range(round(duration * FPS)):
            image = Image.new("RGB", (320, 480), "#f1e8d7")
            d = ImageDraw.Draw(image)
            t = i / FPS
            d.text((24, 20), "DEMO / SYNTHETIC FOOTAGE", fill="#5a4737")
            preparation = hook == "preparation" if t < 2 else True
            if preparation:
                d.rounded_rectangle(
                    (70, 190, 230, 340),
                    radius=18,
                    fill="#fffaf1",
                    outline="#5a4737",
                    width=3,
                )
                d.ellipse(
                    (70, 175, 230, 215), fill="#70472f", outline="#5a4737", width=3
                )
                d.line((160, 95, 160, 192), fill="#a87542", width=6 + i % 4)
                d.arc((210, 220, 275, 300), 260, 100, fill="#5a4737", width=8)
                d.text((90, 365), "A BETTER MORNING", fill="#5a4737")
            else:
                d.rounded_rectangle((90, 130, 230, 345), radius=7, fill="#784b35")
                d.rectangle((105, 195, 215, 275), fill="#e9d2ad")
                d.text((122, 222), "FIELD COFFEE", fill="#482f20")
            d.rectangle((0, 420, 320, 480), fill="#324b3d")
            d.text(
                (80, 442),
                "BREW YOUR NEXT CUP" if t >= 6 else "FIELD / SMALL BATCH",
                fill="white",
            )
            image.save(root / f"{i:05d}.png")
        _run(
            [
                "-framerate",
                str(FPS),
                "-i",
                str(root / "%05d.png"),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-y",
                str(path),
            ]
        )


def extract_audio(path: Path, out: Path) -> Path:
    metadata = probe(path)
    if not metadata["has_audio"]:
        raise MediaError("This video contains no audio stream.")
    out = Path(out)
    _run(
        [
            *_input(path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(out),
        ],
        timeout=30,
    )
    if not out.is_file() or out.stat().st_size > 8 * 1024 * 1024:
        raise MediaError("Extracted audio exceeds its 8 MiB bound.")
    return out
