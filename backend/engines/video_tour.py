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


def build_video_tour(image_b64_list: list[str], styles: list[str] | None = None) -> tuple[Path, dict]:
    """Assemble the given base64 PNG frames into an MP4 tour.

    Args:
        image_b64_list: 2..8 PNG images (base64, no data: prefix).
        styles: optional list of style names (same length) — used for logging only.

    Returns:
        (mp4_path, meta) where meta = {video_id, duration_s, size_bytes, styles, frame_count}.

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

        # 3) Concat with crossfade transitions between clips
        out_path = VIDEO_CACHE_DIR / f"{video_id}.mp4"
        if len(clip_paths) == 1:
            shutil.copy(clip_paths[0], out_path)
        else:
            # Build xfade chain: [0][1]xfade=transition=fade:duration=0.5:offset=X[v1];
            # [v1][2]xfade=...; etc.
            inputs = []
            for cp in clip_paths:
                inputs += ["-i", str(cp)]
            filter_parts = []
            transition_d = 0.5
            offset = FRAME_DURATION_S - transition_d
            prev_label = "0:v"
            for i in range(1, len(clip_paths)):
                out_label = f"v{i}"
                filter_parts.append(
                    f"[{prev_label}][{i}:v]xfade=transition=fade:"
                    f"duration={transition_d}:offset={offset:.3f}[{out_label}]"
                )
                prev_label = out_label
                offset += FRAME_DURATION_S - transition_d
            filter_complex = ";".join(filter_parts)
            cmd = [
                ffmpeg, "-y", *inputs, "-filter_complex", filter_complex,
                "-map", f"[{prev_label}]",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-preset", "veryfast", "-crf", "23",
                "-movflags", "+faststart",
                str(out_path),
            ]
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=180)  # noqa: S603
            except subprocess.CalledProcessError as e:
                logger.error(f"ffmpeg concat failed: {e.stderr.decode()[-500:]}")
                raise RuntimeError("ffmpeg concat failed") from e

    frame_count = len(image_b64_list)
    duration_s = round(frame_count * FRAME_DURATION_S - (frame_count - 1) * 0.5, 1)
    meta = {
        "video_id": video_id,
        "duration_s": duration_s,
        "size_bytes": out_path.stat().st_size,
        "styles": styles or [],
        "frame_count": frame_count,
    }
    return out_path, meta


def get_video_path(video_id: str) -> Path | None:
    """Return path if video file exists on disk, else None."""
    p = VIDEO_CACHE_DIR / f"{video_id}.mp4"
    return p if p.is_file() else None
