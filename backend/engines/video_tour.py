"""Video tour engine — assemble N still images (base64 PNG) into an MP4 slideshow
with Ken Burns effect (zoom / pan) + smooth crossfades. Uses ffmpeg subprocess.

Used by /api/takeoffs/{plan_id}/render-video to produce a "wow" demo attachment
for quotes.
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
import shutil
import subprocess  # noqa: S404 (needed for ffmpeg cli; controlled args)
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

VIDEO_CACHE_DIR = Path(os.getenv("VIDEO_CACHE_DIR", "/app/backend/video_cache"))
VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Per-frame duration in seconds; total video = N * FRAME_DURATION_S
FRAME_DURATION_S = 5.0
# Ken Burns zoom factor (1.0 = no zoom, 1.25 = zoom to 125% at end)
ZOOM_END = 1.20
# Output resolution
OUT_W, OUT_H = 1280, 720
# Frames per second
FPS = 30


def _which_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not installed on this system")
    return path


def _kenburns_filter(direction: str) -> str:
    """Return ffmpeg zoompan filter string. direction rotates zoom center."""
    frames = int(FRAME_DURATION_S * FPS)
    zoom_delta = ZOOM_END - 1.0
    # zoom expr: linear ramp from 1.0 to ZOOM_END over `frames`
    z_expr = f"'if(lte(on,1),1.0,min(zoom+{zoom_delta / frames:.6f},{ZOOM_END}))'"
    # x/y depend on direction (centered zoom by default)
    centers = {
        "center": ("iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
        "topleft": ("0", "0"),
        "topright": ("iw-(iw/zoom)", "0"),
        "bottomleft": ("0", "ih-(ih/zoom)"),
        "bottomright": ("iw-(iw/zoom)", "ih-(ih/zoom)"),
    }
    xe, ye = centers.get(direction, centers["center"])
    return (
        f"scale=-2:{OUT_H * 2},"
        f"zoompan=z={z_expr}:x='{xe}':y='{ye}':d={frames}:"
        f"s={OUT_W}x{OUT_H}:fps={FPS}"
    )


def build_video_tour(image_b64_list: list[str], styles: list[str] | None = None,
                     logo_bytes: bytes | None = None,
                     add_audio: bool = True) -> tuple[Path, dict]:
    """Assemble the given base64 PNG frames into an MP4 tour.

    Args:
        image_b64_list: 2..8 PNG images (base64, no data: prefix).
        styles: optional list of style names (same length) — used for logging only.
        logo_bytes: optional PNG/JPEG bytes to overlay in the top-right corner
            of every frame (~15% of video width, semi-transparent).
        add_audio: if True, mix a soft ambient C-major triad synth pad under
            the video (fade in/out, low volume).

    Returns:
        (mp4_path, meta) where meta = {video_id, duration_s, size_bytes, styles,
        frame_count, has_watermark, has_audio}.

    Raises RuntimeError if ffmpeg fails.
    """
    if not image_b64_list:
        raise ValueError("empty image list")
    if len(image_b64_list) > 8:
        raise ValueError("max 8 frames")

    ffmpeg = _which_ffmpeg()
    video_id = "v3d_" + secrets.token_hex(5)
    directions = ["center", "topleft", "topright", "bottomright", "bottomleft",
                  "center", "topleft", "topright"]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        # 1) Decode images to disk
        img_paths: list[Path] = []
        for i, b64 in enumerate(image_b64_list):
            data = base64.b64decode(b64)
            p = tmp / f"frame_{i:02d}.png"
            p.write_bytes(data)
            img_paths.append(p)

        # 2) Per-image Ken Burns clip
        clip_paths: list[Path] = []
        for i, img_path in enumerate(img_paths):
            clip = tmp / f"clip_{i:02d}.mp4"
            direction = directions[i % len(directions)]
            cmd = [
                ffmpeg, "-y", "-loop", "1", "-i", str(img_path),
                "-t", str(FRAME_DURATION_S),
                "-vf", _kenburns_filter(direction),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-preset", "veryfast", "-crf", "23",
                str(clip),
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=60)  # noqa: S603
            except subprocess.CalledProcessError as e:
                logger.error(f"ffmpeg clip {i} failed: {e.stderr.decode()[-500:]}")
                raise RuntimeError(f"ffmpeg clip {i} failed") from e
            clip_paths.append(clip)

        # 3) Save logo to disk (if provided)
        logo_path: Path | None = None
        if logo_bytes:
            logo_path = tmp / "logo.png"
            logo_path.write_bytes(logo_bytes)

        # 4) Concat with crossfade transitions + optional watermark + optional audio
        out_path = VIDEO_CACHE_DIR / f"{video_id}.mp4"
        _concat_and_finalize(
            ffmpeg=ffmpeg,
            clip_paths=clip_paths,
            out_path=out_path,
            logo_path=logo_path,
            add_audio=add_audio,
        )

    frame_count = len(image_b64_list)
    duration_s = round(frame_count * FRAME_DURATION_S - (frame_count - 1) * 0.5, 1)
    meta = {
        "video_id": video_id,
        "duration_s": duration_s,
        "size_bytes": out_path.stat().st_size,
        "styles": styles or [],
        "frame_count": frame_count,
        "has_watermark": bool(logo_bytes),
        "has_audio": add_audio,
    }
    return out_path, meta


def _concat_and_finalize(*, ffmpeg: str, clip_paths: list[Path], out_path: Path,
                         logo_path: Path | None, add_audio: bool) -> None:
    """Concat N per-clip mp4s with xfade, then overlay logo + mix ambient audio."""
    n_clips = len(clip_paths)
    transition_d = 0.5
    total_video_d = n_clips * FRAME_DURATION_S - (n_clips - 1) * transition_d

    # Build inputs (track ffmpeg input indices carefully — lavfi is still one input each)
    inputs: list[str] = []
    input_idx = 0
    for cp in clip_paths:
        inputs += ["-i", str(cp)]
        input_idx += 1
    logo_idx = None
    if logo_path is not None:
        inputs += ["-i", str(logo_path)]
        logo_idx = input_idx
        input_idx += 1

    # Audio inputs via lavfi (C-major triad pad + gentle low sine bass)
    audio_indices: list[int] = []
    if add_audio:
        for freq in (261.63, 329.63, 392.00, 130.81):
            inputs += ["-f", "lavfi", "-i",
                       f"sine=frequency={freq}:duration={total_video_d:.2f}:sample_rate=44100"]
            audio_indices.append(input_idx)
            input_idx += 1

    # Build video filter graph
    filter_parts: list[str] = []
    if n_clips == 1:
        video_label = "0:v"
    else:
        offset = FRAME_DURATION_S - transition_d
        prev_label = "0:v"
        for i in range(1, n_clips):
            out_label = f"vx{i}"
            filter_parts.append(
                f"[{prev_label}][{i}:v]xfade=transition=fade:"
                f"duration={transition_d}:offset={offset:.3f}[{out_label}]"
            )
            prev_label = out_label
            offset += FRAME_DURATION_S - transition_d
        video_label = prev_label

    # Overlay logo (top-right, 15% of video width, semi-transparent)
    if logo_idx is not None:
        # Scale logo to 15 % of output width, keep aspect ratio, add alpha channel
        filter_parts.append(
            f"[{logo_idx}:v]format=rgba,colorchannelmixer=aa=0.85,"
            f"scale=w=iw*0.15:h=-1[logo]"
        )
        filter_parts.append(
            f"[{video_label}][logo]overlay=W-w-24:24:format=auto[vout]"
        )
        video_label = "vout"

    # Audio filter graph
    audio_map: list[str] = []
    if add_audio and audio_indices:
        parts = "".join(f"[{i}:a]" for i in audio_indices)
        filter_parts.append(
            f"{parts}amix=inputs={len(audio_indices)}:duration=first,"
            f"volume=0.05,"
            f"afade=in:st=0:d=1.5,"
            f"afade=out:st={max(0, total_video_d - 1.5):.2f}:d=1.5[aout]"
        )
        audio_map = ["-map", "[aout]", "-c:a", "aac", "-b:a", "128k"]

    filter_complex = ";".join(filter_parts) if filter_parts else None

    cmd: list[str] = [ffmpeg, "-y", *inputs]
    if filter_complex:
        cmd += ["-filter_complex", filter_complex, "-map", f"[{video_label}]"]
    else:
        # No filter graph at all (single clip, no logo, no audio) → just remux
        cmd += ["-map", "0:v", "-c", "copy", str(out_path)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)  # noqa: S603
        except subprocess.CalledProcessError as e:
            logger.error(f"ffmpeg copy failed: {e.stderr.decode()[-500:]}")
            raise RuntimeError("ffmpeg copy failed") from e
        return

    cmd += audio_map
    cmd += [
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "veryfast", "-crf", "23",
        "-movflags", "+faststart",
        str(out_path),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)  # noqa: S603
    except subprocess.CalledProcessError as e:
        logger.error(f"ffmpeg finalize failed: {e.stderr.decode()[-800:]}")
        raise RuntimeError("ffmpeg finalize failed") from e


def get_video_path(video_id: str) -> Path | None:
    """Return path if video file exists on disk, else None."""
    p = VIDEO_CACHE_DIR / f"{video_id}.mp4"
    return p if p.is_file() else None
