import asyncio
import os
import tempfile
from io import BytesIO
from pathlib import Path
from typing import List

from PIL import Image


TARGET_FPS = 30
GRID_MS = 1000 / TARGET_FPS


def is_animated_webp(data: bytes) -> bool:
    return len(data) >= 16 and data[:4] == b"RIFF" and b"VP8X" in data[:16]


def parse_webp_frame_durations(data: bytes) -> List[int]:
    """ANMF chunk별 frame duration(ms). Pillow info['duration']이 카카오 WebP에서 0을 돌려주는 이슈 우회용."""
    if not is_animated_webp(data) or data[8:12] != b"WEBP":
        return []
    pos = 12
    durations: List[int] = []
    while pos < len(data) - 8:
        fourcc = data[pos:pos + 4]
        size = int.from_bytes(data[pos + 4:pos + 8], "little")
        if fourcc == b"ANMF":
            dur = int.from_bytes(data[pos + 8 + 12:pos + 8 + 15], "little")
            durations.append(max(dur, 1))
        pos += 8 + size + (size & 1)
    return durations


def build_frame_sequence(durations_ms: List[int]) -> List[int]:
    """frame별 ms duration을 30fps grid 위 누적 매핑.

    텔레그램이 webm container PTS를 무시하고 30fps cfr로 재생하기 때문에,
    각 source frame을 grid 횟수만큼 PNG로 duplicate해서 인코딩한다.
    누적 rounding으로 drift 최소화."""
    sequence: List[int] = []
    cumulative = 0
    next_grid = 0
    for i, dur in enumerate(durations_ms):
        cumulative += dur
        new_grid = round(cumulative / GRID_MS)
        sequence.extend([i] * max(new_grid - next_grid, 1))
        next_grid = new_grid
    return sequence


async def webp_to_webm(webp_bytes: bytes) -> bytes:
    img = Image.open(BytesIO(webp_bytes))
    n_frames = img.n_frames
    durations_ms = parse_webp_frame_durations(webp_bytes)
    if len(durations_ms) != n_frames:
        durations_ms = [80] * n_frames

    sequence = build_frame_sequence(durations_ms)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src_dir = tmp / "src"
        seq_dir = tmp / "seq"
        src_dir.mkdir()
        seq_dir.mkdir()

        for i in range(n_frames):
            img.seek(i)
            img.convert("RGBA").save(src_dir / f"{i:04d}.png")

        for j, src_idx in enumerate(sequence):
            os.link(src_dir / f"{src_idx:04d}.png", seq_dir / f"{j:05d}.png")

        out = tmp / "out.webm"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-framerate", str(TARGET_FPS),
            "-i", str(seq_dir / "%05d.png"),
            "-c:v", "libvpx-vp9",
            "-b:v", "200k",
            "-vf",
            "scale=512:512:force_original_aspect_ratio=decrease,"
            "pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000",
            "-pix_fmt", "yuva420p",
            "-t", "3",
            "-an",
            str(out),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {err.decode(errors='replace')[:500]}")
        return out.read_bytes()
