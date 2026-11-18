"""Turn rendered reel frames (assets/<id>/slide-NN.png) into assets/<id>/reel.mp4 with a calm BGM track.

Usage: python scripts/make_reel.py assets/Q-001-en   (called by render.py for style "reel")
"""
from __future__ import annotations

import subprocess
import sys
import zlib
from pathlib import Path

import imageio_ffmpeg

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bgm  # noqa: E402

HOLD = 3.2      # seconds each frame is fully visible
FADE = 0.5      # crossfade length
FIRST = 3.6     # first frame stays a little longer (hook)
LAST = 4.6      # last frame (CTA) stays longer


def build(out_dir: Path, seed_text: str) -> Path:
    frames = sorted(out_dir.glob("slide-*.png"))
    if not frames:
        raise SystemExit(f"no frames in {out_dir}")
    n = len(frames)
    durs = [HOLD] * n
    durs[0] = FIRST
    durs[-1] = LAST
    # each input clip must also cover the fade into the next one
    clip = [d + (FADE if i < n - 1 else 0) for i, d in enumerate(durs)]
    total = sum(durs)
    wav = out_dir / "bgm.wav"
    bgm.write_wav(str(wav), bgm.make(total, zlib.crc32(seed_text.encode()) % 1000))

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [ff, "-y", "-loglevel", "error"]
    for f, c in zip(frames, clip):
        cmd += ["-loop", "1", "-framerate", "30", "-t", f"{c:.3f}", "-i", str(f)]
    cmd += ["-i", str(wav)]
    parts, last, offset = [], "0:v", 0.0
    for i in range(n):
        parts.append(f"[{i}:v]scale=1080:1920,setsar=1,format=yuv420p,fps=30[v{i}]")
    last = "v0"
    for i in range(1, n):
        offset += durs[i - 1]
        nxt = f"x{i}"
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={FADE}:offset={offset - 0:.3f}[{nxt}]")
        last = nxt
    filt = ";".join(parts)
    out = out_dir / "reel.mp4"
    cmd += ["-filter_complex", filt, "-map", f"[{last}]", "-map", f"{n}:a",
            "-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    wav.unlink(missing_ok=True)
    return out


if __name__ == "__main__":
    d = Path(sys.argv[1])
    print(build(d, d.name))
