"""Synthesise original, royalty-free background music for the reels (no samples, no licences needed).

Styles:
  uke   — bright ukulele strums + glockenspiel melody + shaker (cute, webtoon-like)
  lofi  — soft Rhodes chords, warm bass, gentle swung drums, vinyl texture
  box   — music-box lullaby over a soft pad
Usage: python scripts/bgm.py OUT.wav SECONDS [SEED] [STYLE]
"""
from __future__ import annotations

import sys
import wave

import numpy as np

SR = 44100
STYLES = ["uke", "lofi", "box"]
DEFAULT_STYLE = "uke"  # chosen by the clinic (2026-11-18)

PROG = {
    "uke":  [[60, 64, 67, 72], [65, 69, 72, 77], [67, 71, 74, 79], [69, 72, 76, 81]],      # C F G Am
    "uke2": [[67, 71, 74, 79], [64, 67, 71, 76], [60, 64, 67, 72], [62, 66, 69, 74]],      # G Em C D
    "lofi": [[53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [55, 59, 62, 65]],      # Fmaj7 Em7 Dm7 G7
    "lofi2": [[50, 53, 57, 60], [55, 59, 62, 65], [48, 52, 55, 59], [45, 48, 52, 55]],     # Dm7 G7 Cmaj7 Am7
    "box":  [[60, 64, 67], [57, 60, 64], [53, 57, 60], [55, 59, 62]],                       # C Am F G
}


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def t_(dur: float) -> np.ndarray:
    return np.arange(int(SR * dur)) / SR


def onepole(x: np.ndarray, cutoff: float) -> np.ndarray:
    """Vectorised-enough one-pole low-pass via scipy-free IIR (block recursion)."""
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    b = 1 - a
    # process in python but on float arrays; tracks are short (≤ 60 s)
    for i in range(len(x)):
        acc = b * x[i] + a * acc
        y[i] = acc
    return y


def pluck(freq: float, dur: float, bright: float = 0.6, decay: float = 0.996, rng=None) -> np.ndarray:
    """Karplus-Strong string (ukulele/guitar-like), block-vectorised."""
    rng = rng or np.random.default_rng()
    n = int(SR * dur)
    N = max(2, int(SR / freq))
    buf = rng.uniform(-1, 1, N)
    # soften the excitation for a nylon-string feel
    for _ in range(int((1 - bright) * 4)):
        buf = 0.5 * (buf + np.roll(buf, 1))
    out = np.empty(n)
    out[:N] = buf[: min(N, n)]
    i = N
    while i < n:
        prev = out[i - N:i]
        blk = decay * 0.5 * (prev + np.concatenate(([out[i - N - 1] if i - N - 1 >= 0 else 0.0], prev[:-1])))
        k = min(N, n - i)
        out[i:i + k] = blk[:k]
        i += k
    env = np.minimum(1, t_(dur) / 0.002)
    return out * env


def bell(freq: float, dur: float, vel: float = 0.3) -> np.ndarray:
    t = t_(dur)
    sig = (np.sin(2 * np.pi * freq * t) * np.exp(-t * 3.0)
           + 0.35 * np.sin(2 * np.pi * freq * 2.76 * t) * np.exp(-t * 6)
           + 0.15 * np.sin(2 * np.pi * freq * 5.40 * t) * np.exp(-t * 11)
           + 0.08 * np.sin(2 * np.pi * freq * 8.93 * t) * np.exp(-t * 18))
    return vel * sig * np.minimum(1, t / 0.001)


def musicbox(freq: float, dur: float, vel: float = 0.25) -> np.ndarray:
    t = t_(dur)
    sig = (np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * freq * 3.0 * t) * np.exp(-t * 4)
           + 0.25 * np.sin(2 * np.pi * freq * 4.2 * t) * np.exp(-t * 9))
    return vel * sig * np.exp(-t * 2.2) * np.minimum(1, t / 0.0015)


def rhodes(freq: float, dur: float, vel: float = 0.25) -> np.ndarray:
    t = t_(dur)
    idx = 1.6 * np.exp(-t * 3.5) + 0.2
    mod = np.sin(2 * np.pi * freq * t)
    car = np.sin(2 * np.pi * freq * t + idx * mod)
    tine = 0.12 * np.sin(2 * np.pi * freq * 7 * t) * np.exp(-t * 14)
    env = np.exp(-t * 1.3) * np.minimum(1, t / 0.004) * (1 - np.clip((t - dur + 0.15) / 0.15, 0, 1))
    trem = 1 + 0.12 * np.sin(2 * np.pi * 4.5 * t)
    return vel * (car + tine) * env * trem


def pad(freqs: list[float], dur: float, vel: float = 0.04) -> np.ndarray:
    t = t_(dur)
    env = np.minimum(1, t / 1.0) * np.clip((dur - t) / 1.0, 0, 1)
    sig = sum(np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 1.004 * t + 1) + 0.25 * np.sin(2 * np.pi * f * 2 * t) for f in freqs)
    return vel * env * sig


def kick(vel=0.5) -> np.ndarray:
    t = t_(0.35)
    f = 50 + 70 * np.exp(-t * 30)
    return vel * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def noise_hit(dur, decay, vel, cutoff_hi=True, rng=None) -> np.ndarray:
    rng = rng or np.random.default_rng()
    t = t_(dur)
    n = rng.normal(0, 1, len(t))
    if cutoff_hi:
        n = n - np.concatenate(([0], n[:-1]))  # crude high-pass
    return vel * n * np.exp(-t * decay)


def snare(vel=0.25, rng=None) -> np.ndarray:
    t = t_(0.25)
    return noise_hit(0.25, 22, vel * 0.6, rng=rng) + vel * 0.5 * np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25)


def reverb(x: np.ndarray, wet: float = 0.35) -> np.ndarray:
    out = x.copy()
    for d, g in [(0.029, 0.5), (0.037, 0.45), (0.053, 0.4), (0.079, 0.33), (0.113, 0.27), (0.163, 0.2), (0.229, 0.14), (0.311, 0.09)]:
        k = int(d * SR)
        out[k:] += wet * g * x[:-k]
    return out


class Track:
    def __init__(self, seconds: float):
        self.n = int(SR * (seconds + 4))
        self.mix = np.zeros(self.n)

    def add(self, sig: np.ndarray, at: float, gain: float = 1.0) -> None:
        i = max(0, int(at * SR))
        if i >= self.n:
            return
        j = min(self.n, i + len(sig))
        self.mix[i:j] += gain * sig[: j - i]


def style_uke(seconds, rng):
    pr = PROG["uke"] if rng.random() < 0.5 else PROG["uke2"]
    bpm = 96 + int(rng.integers(0, 10))
    beat = 60 / bpm
    tr, drums = Track(seconds), Track(seconds)
    t, ci = 0.0, 0
    strum = [(0, 1.0, 'd'), (1, 0.55, 'd'), (1.5, 0.45, 'u'), (2.5, 0.5, 'u'), (3, 0.7, 'd'), (3.5, 0.45, 'u')]
    mel_scale = [72, 74, 76, 79, 81, 84]
    while t < seconds + 1:
        ch = pr[ci % 4]
        for pos, vel, d in strum:
            notes = ch if d == 'd' else ch[::-1]
            for k, m in enumerate(notes):
                tr.add(pluck(hz(m), 1.4, 0.55, 0.9965, rng), t + pos * beat + k * 0.012, 0.16 * vel)
        drums.add(kick(0.2), t)
        drums.add(kick(0.14), t + 2 * beat)
        for e in range(8):
            drums.add(noise_hit(0.06, 70, 0.025 if e % 2 else 0.04, rng=rng), t + e * beat / 2)
        # glockenspiel motif, every bar a little phrase
        if ci % 2 == 0 or rng.random() < 0.6:
            phrase = rng.choice(len(mel_scale), size=3)
            for k, idx in enumerate(phrase):
                m = mel_scale[idx]
                if m % 12 not in [x % 12 for x in ch] and rng.random() < 0.6:
                    m = ch[rng.integers(0, len(ch))] + 12
                tr.add(bell(hz(m), 1.6, 0.11), t + (k * 1.0 + (0.5 if k == 2 else 0)) * beat)
        t += 4 * beat
        ci += 1
    return reverb(tr.mix, 0.25) + drums.mix


def style_lofi(seconds, rng):
    pr = PROG["lofi"] if rng.random() < 0.5 else PROG["lofi2"]
    bpm = 74 + int(rng.integers(0, 8))
    beat = 60 / bpm
    sw = 0.08 * beat  # swing
    tr, drums = Track(seconds), Track(seconds)
    t, ci = 0.0, 0
    while t < seconds + 1:
        ch = pr[ci % 4]
        for k, m in enumerate(ch):
            tr.add(rhodes(hz(m), 4 * beat * 0.95, 0.07), t + k * 0.018)
        tr.add(rhodes(hz(ch[0] - 12), 4 * beat, 0.12), t)
        tr.add(np.sin(2 * np.pi * hz(ch[0] - 24) * t_(beat * 1.8)) * np.exp(-t_(beat * 1.8) * 1.5) * 0.22, t)
        tr.add(np.sin(2 * np.pi * hz(ch[0] - 24) * t_(beat * 1.2)) * np.exp(-t_(beat * 1.2) * 2) * 0.16, t + 2.5 * beat)
        # a few lazy melody notes
        for k in range(int(rng.integers(1, 4))):
            m = ch[rng.integers(1, len(ch))] + 12
            tr.add(rhodes(hz(m), beat * 1.5, 0.05), t + rng.choice([0.5, 1.5, 2, 3]) * beat)
        drums.add(kick(0.45), t)
        drums.add(kick(0.3), t + 2.5 * beat)
        drums.add(snare(0.16, rng), t + beat)
        drums.add(snare(0.16, rng), t + 3 * beat)
        for e in range(8):
            drums.add(noise_hit(0.05, 80, 0.02, rng=rng), t + e * beat / 2 + (sw if e % 2 else 0))
        t += 4 * beat
        ci += 1
    d = onepole(drums.mix, 5000)
    music = onepole(reverb(tr.mix, 0.3), 4200)
    vinyl = (rng.random(len(music)) < 0.0008) * rng.normal(0, 0.15, len(music)) + onepole(rng.normal(0, 0.006, len(music)), 1500)
    return music + d + vinyl


def style_box(seconds, rng):
    pr = PROG["box"]
    bpm = 84 + int(rng.integers(0, 8))
    beat = 60 / bpm
    tr = Track(seconds)
    t, ci = 0.0, 0
    while t < seconds + 1:
        ch = pr[ci % 4]
        tr.add(pad([hz(m) for m in ch], 4 * beat + 1, 0.012), t)
        pattern = [0, 1, 2, 1, 0, 2, 1, 2]
        for k, idx in enumerate(pattern):
            tr.add(musicbox(hz(ch[idx] + 12), 1.8, 0.07), t + k * beat / 2)
        m = ch[rng.integers(0, len(ch))] + 24
        tr.add(musicbox(hz(m), 2.2, 0.09), t + beat * rng.choice([0, 1, 2]))
        t += 4 * beat
        ci += 1
    return reverb(tr.mix, 0.45)


def make(seconds: float, seed: int = 0, style: str | None = None) -> np.ndarray:
    rng = np.random.default_rng(seed)
    style = style or DEFAULT_STYLE
    x = {"uke": style_uke, "lofi": style_lofi, "box": style_box}[style](seconds, rng)
    x = x[: int(SR * seconds)]
    x = x - x.mean()
    x = x / max(1e-6, np.percentile(np.abs(x), 99.7))
    x = np.tanh(x * 0.9) * 0.55  # gentle limiting
    fi, fo = int(SR * 0.8), int(SR * 2.5)
    x[:fi] *= np.linspace(0, 1, fi)
    x[-fo:] *= np.linspace(1, 0, fo)
    return x


def write_wav(path: str, x: np.ndarray) -> None:
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    stereo = np.stack([pcm, pcm], axis=1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())


if __name__ == "__main__":
    out, secs = sys.argv[1], float(sys.argv[2])
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    style = sys.argv[4] if len(sys.argv) > 4 else None
    write_wav(out, make(secs, seed, style))
    print(f"wrote {out} ({secs:.1f}s, style {style or DEFAULT_STYLE})")
