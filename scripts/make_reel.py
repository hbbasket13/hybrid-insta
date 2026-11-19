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
MUSIC = False   # synthesised BGM off (clinic preference, 2026-11-18)
MUSIC_DIR = Path(__file__).resolve().parent.parent / "music"   # clinic-supplied royalty-free tracks, stored as <name>.m4a.b64
MUSIC_GAIN_DB = -3.0


def _tracks() -> list[Path]:
    """Decode music/*.b64 into a cache once; returns playable files."""
    import base64
    cache = Path("/tmp/reel_music"); cache.mkdir(exist_ok=True)
    out = []
    for b in sorted(MUSIC_DIR.glob("*.b64")):
        dst = cache / b.name[:-4]
        if not dst.exists():
            dst.write_bytes(base64.b64decode(b.read_text().strip()))
        out.append(dst)
    return out


def _duration(ff: str, f: Path) -> float:
    import re
    r = subprocess.run([ff, "-i", str(f)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def music_version() -> str:
    names = ",".join(b.name + str(b.stat().st_size) for b in sorted(MUSIC_DIR.glob("*.b64")))
    return f"v2:{MUSIC}:{zlib.crc32(names.encode())}"


def is_stale(out_dir: Path) -> bool:
    """True when reel.mp4 was built with a different music set than the current one."""
    import json
    m = out_dir / "reel.json"
    if not (out_dir / "reel.mp4").exists():
        return True
    try:
        return json.loads(m.read_text()).get("music") != music_version()
    except Exception:
        return True


def music_for(seed_text: str, total: float, ff: str, out: Path) -> bool:
    """Pick a track (stable per episode) and a start point, write a faded, levelled clip to `out`."""
    import random
    tracks = _tracks()
    if not tracks:
        return False
    rnd = random.Random(zlib.crc32(seed_text.encode()))
    tr = rnd.choice(tracks)
    dur = _duration(ff, tr)
    start = 0.0 if dur < total + 8 else rnd.uniform(0, min(40.0, dur - total - 4))
    fade_out = max(0.0, total - 2.5)
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{total:.3f}", "-i", str(tr),
                    "-af", f"afade=t=in:d=0.4,afade=t=out:st={fade_out:.2f}:d=2.5,loudnorm=I=-16:TP=-1.5:LRA=11,volume={MUSIC_GAIN_DB}dB",
                    "-ar", "44100", "-ac", "2", str(out)], check=True)
    return True


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
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    if music_for(seed_text, total, ff, wav):
        pass
    elif MUSIC:
        bgm.write_wav(str(wav), bgm.make(total, zlib.crc32(seed_text.encode()) % 1000))
    else:
        import numpy as np
        bgm.write_wav(str(wav), np.zeros(int(bgm.SR * total)))
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
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-shortest", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    wav.unlink(missing_ok=True)
    import json
    (out_dir / "reel.json").write_text(json.dumps({"music": music_version()}))
    return out


if __name__ == "__main__":
    d = Path(sys.argv[1])
    print(build(d, d.name))
