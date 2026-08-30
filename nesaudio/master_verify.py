#!/usr/bin/env python3
"""Master + verify a generated take against its source SFX.

Ports the rules from spark-vault wiki/playbooks/sfx-pipeline.md and
sfx-verification.md: Stable Audio runs hot and fills the whole latent, so every
take is trimmed, one-shot-extracted, peak-normalised, then measured rather than
trusted.
"""
import subprocess, sys, os, json
import numpy as np

SR = 44100
ONESHOT_ATTACK_MAX = 0.025   # s -- bounded backward walk (unbounded ran to 1965ms)
FLOOR = 0.08                 # attack leaves the noise floor at ~8% of peak
ARM, REARM = 0.60, 0.25      # event-count hysteresis


def load(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1",
                          "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def audible_span(x, rel=0.02):
    e = np.abs(x)
    if e.max() <= 0:
        return 0, 0
    idx = np.where(e > e.max() * rel)[0]
    return (idx[0], idx[-1]) if len(idx) else (0, 0)


def oneshot(x, keep):
    """Anchor on the loudest sample, walk BACK to the attack, bounded."""
    pk = int(np.argmax(np.abs(x)))
    thr = np.abs(x[pk]) * FLOOR
    lim = max(0, pk - int(ONESHOT_ATTACK_MAX * SR))
    i = pk
    while i > lim and abs(x[i]) > thr:
        i -= 1
    start = max(0, i - int(0.008 * SR))          # cut 8 ms before
    return x[start:start + int(keep * SR)]


def master(x, fade_in=0.005, fade_out=0.030):
    a, b = audible_span(x)
    x = x[a:b + 1] if b > a else x
    if not len(x):
        return x
    pk = np.abs(x).max()
    if pk > 0:
        x = x * (10 ** (-1.0 / 20) / pk)          # peak-normalise to -1 dBFS
    n_i, n_o = int(fade_in * SR), int(fade_out * SR)
    if len(x) > n_i + n_o:
        x[:n_i] *= np.linspace(0, 1, n_i)
        x[-n_o:] *= np.linspace(1, 0, n_o)
    return x


def db(v):
    return 20 * np.log10(max(v, 1e-12))


def count_events(x):
    e = np.abs(x)
    if e.max() <= 0:
        return 0
    e = e / e.max()
    n, armed = 0, True
    for v in e:
        if armed and v > ARM:
            n += 1
            armed = False
        elif not armed and v < REARM:
            armed = True
    return n


def envelope(x, cols=60):
    if not len(x) or np.abs(x).max() <= 0:
        return " " * cols
    e = np.abs(x) / np.abs(x).max()
    ramp = " .:-=+*#%@"
    out = []
    for i in range(cols):
        seg = e[i * len(e) // cols:(i + 1) * len(e) // cols]
        out.append(ramp[min(9, int((seg.max() if len(seg) else 0) * 9.99))])
    return "".join(out)


def band_frac(x, lo, hi):
    X = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    fr = np.fft.rfftfreq(len(x), 1 / SR)
    return X[(fr >= lo) & (fr < hi)].sum() / max(X.sum(), 1e-12)


def verify(x, ref, events_budget=1):
    """Compare a mastered take against the mastered source."""
    f = []
    a, b = audible_span(x)
    span = (b - a) / SR
    if db(np.sqrt((x ** 2).mean())) < -45: f.append("SILENT")
    if db(np.abs(x).max()) > -0.5:         f.append("CLIPPED")
    if span < 0.03:                        f.append("TOO-SHORT")
    if a / SR > 0.035:                     f.append("LATE-ATTACK")
    n = count_events(x)
    if n > events_budget:                  f.append(f"MULTI-EVENT({n})")
    # spectral match against the reference, not an absolute band rule
    for lo, hi, name in [(0, 200, "low"), (200, 2000, "mid"), (2000, 22050, "high")]:
        gx, gr = band_frac(x, lo, hi), band_frac(ref, lo, hi)
        if abs(gx - gr) > 0.30:
            f.append(f"TONE-{name.upper()}({gx:.2f}vs{gr:.2f})")
    return f, span, n


def write(path, x):
    """Write mono data as a dual-mono stereo WAV.

    NOT `-ac 2`: ffmpeg's mono->stereo upmix applies a -3 dB pan law, so a
    signal peak-normalised to -1 dBFS lands on disk at -4. `pan` copies the
    channel at unity instead.
    """
    p = subprocess.Popen(["ffmpeg", "-v", "quiet", "-y", "-f", "f32le", "-ar", str(SR),
                          "-ac", "1", "-i", "-",
                          "-af", "pan=stereo|c0=c0|c1=c0", path], stdin=subprocess.PIPE)
    p.communicate(x.astype(np.float32).tobytes())


if __name__ == "__main__":
    ref_path, keep = sys.argv[1], float(sys.argv[2])
    ref = master(load(ref_path))
    print(f"REF  {os.path.basename(ref_path):<28} {envelope(ref)}  "
          f"span={len(ref)/SR:.2f}s events={count_events(ref)}")
    for t in sys.argv[3:]:
        x = master(oneshot(load(t), keep))
        f, span, n = verify(x, ref)
        out = t.rsplit(".", 1)[0] + "_mastered.wav"
        write(out, x)
        print(f"TAKE {os.path.basename(t):<28} {envelope(x)}  "
              f"span={span:.2f}s events={n}  {'OK' if not f else ' '.join(f)}")
