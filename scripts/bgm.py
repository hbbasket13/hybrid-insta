"""Synthesise a calm, royalty-free background track (soft piano + pad + light texture).

Original music generated from code, so there are no licensing issues.
Usage: python scripts/bgm.py OUT.wav SECONDS [SEED]
"""
from __future__ import annotations

import sys
import wave

import numpy as np

SR = 48000

# chord progressions as MIDI note lists (root position voicings around middle C)
PRESETS = [
    {"bpm": 72, "chords": [[53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [48, 52, 55, 59]]},   # Fmaj7 Em7 Dm7 Cmaj7
    {"bpm": 68, "chords": [[48, 52, 55, 59], [45, 48, 52, 55], [53, 57, 60, 64], [55, 59, 62, 65]]},   # Cmaj7 Am7 Fmaj7 G7
    {"bpm": 76, "chords": [[50, 53, 57, 60], [55, 59, 62, 65], [48, 52, 55, 59], [57, 60, 64, 67]]},   # Dm7 G7 Cmaj7 Am7
    {"bpm": 70, "chords": [[52, 55, 59, 62], [57, 60, 64, 67], [50, 54, 57, 61], [55, 59, 62, 66]]},   # Em7 Am7 Dmaj7 Gmaj7
    {"bpm": 66, "chords": [[46, 50, 53, 57], [51, 55, 58, 62], [48, 51, 55, 58], [53, 57, 60, 63]]},   # Bbmaj7 Ebmaj7 Cm7 F7
]


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def piano(freq: float, dur: float, vel: float = 0.5) -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    env = np.exp(-t * 2.2) * (1 - np.exp(-t * 400))
    sig = sum(a * np.sin(2 * np.pi * freq * k * t) * np.exp(-t * (k - 1) * 0.9) for k, a in [(1, 1.0), (2, 0.42), (3, 0.18), (4, 0.08), (5, 0.04)])
    return vel * env * sig


def pad(freqs: list[float], dur: float) -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    env = np.minimum(1, t / 1.2) * np.minimum(1, (dur - t) / 1.2).clip(0)
    sig = sum(np.sin(2 * np.pi * f * t + np.sin(2 * np.pi * 0.3 * t) * 0.6) + 0.3 * np.sin(2 * np.pi * f * 1.003 * t) for f in freqs)
    return 0.05 * env * sig


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):  # simple one-pole; fine for short tracks
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


def reverb(x: np.ndarray) -> np.ndarray:
    out = x.copy()
    for d, g in [(0.031, 0.32), (0.047, 0.27), (0.071, 0.22), (0.113, 0.17), (0.173, 0.12), (0.241, 0.08)]:
        n = int(d * SR)
        out[n:] += g * x[:-n]
    return out


def make(seconds: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    pr = PRESETS[seed % len(PRESETS)]
    beat = 60.0 / pr["bpm"]
    bar = beat * 4
    n = int(SR * (seconds + 3))
    mix = np.zeros(n)

    def add(sig: np.ndarray, at: float) -> None:
        i = max(0, int(at * SR))
        if i >= n:
            return
        j = min(n, i + len(sig))
        mix[i:j] += sig[: j - i]

    t, ci = 0.0, 0
    while t < seconds + 1:
        ch = pr["chords"][ci % len(pr["chords"])]
        add(pad([hz(m) for m in ch], bar + 0.6), t)
        add(piano(hz(ch[0] - 12), bar * 0.95, 0.30), t)  # bass note
        # gentle broken-chord pattern, a little humanised
        pattern = [0, 2, 1, 3, 2, 1, 3, 2]
        for k, idx in enumerate(pattern):
            if rng.random() < 0.15:
                continue
            m = ch[idx] + (12 if k in (3, 6) else 0)
            add(piano(hz(m), beat * 1.6, 0.16 + rng.random() * 0.06), t + k * beat / 2 + rng.normal(0, 0.008))
        # occasional melody note on top
        if rng.random() < 0.7:
            m = ch[rng.integers(0, 4)] + 12
            add(piano(hz(m), beat * 2.5, 0.20), t + beat * rng.choice([0, 1, 2]))
        t += bar
        ci += 1

    mix = lowpass(mix, 3800)
    mix = reverb(mix)
    mix += rng.normal(0, 0.0025, n) * (rng.random(n) < 0.002) * 6  # faint vinyl ticks
    mix += lowpass(rng.normal(0, 0.004, n), 900)  # soft room hiss
    mix = mix[: int(SR * seconds)]
    fade_in, fade_out = int(SR * 1.0), int(SR * 2.5)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)
    mix[-fade_out:] *= np.linspace(1, 0, fade_out)
    mix /= max(1e-6, np.abs(mix).max())
    return mix * 0.6


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
    write_wav(out, make(secs, seed))
    print(f"wrote {out} ({secs:.1f}s, preset {seed % len(PRESETS)})")
