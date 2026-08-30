"""Estimate 2A03 channel + parameters from an original SFX.

YIN-style cumulative-mean-normalised difference: robust where plain
autocorrelation octave-errors on short, noisy, band-limited chip audio.
"""
import sys, glob, re
import numpy as np
from .master_verify import load, master, SR


def yin(sig, fmin=60, fmax=4000, thresh=0.25):
    tmin, tmax = int(SR/fmax), min(int(SR/fmin), len(sig)//2 - 1)
    if tmax <= tmin: return 0.0, 0.0
    d = np.empty(tmax + 1)
    for t in range(tmin, tmax + 1):
        diff = sig[:len(sig)-tmax] - sig[t:t+len(sig)-tmax]
        d[t] = (diff ** 2).sum()
    d[:tmin] = d[tmin]
    cum = np.cumsum(d[tmin:]) / (np.arange(1, tmax-tmin+2))
    cmnd = np.ones(tmax + 1)
    cmnd[tmin:] = d[tmin:] / np.maximum(cum, 1e-12)
    cand = np.where(cmnd[tmin:tmax] < thresh)[0]
    t = (tmin + cand[0]) if len(cand) else (tmin + int(np.argmin(cmnd[tmin:tmax])))
    return SR / t, float(1.0 - cmnd[t])


def track(x, hop=0.008, win=0.035):
    H, W = int(hop*SR), int(win*SR)
    out = []
    for i in range(0, max(1, len(x)-W), H):
        s = x[i:i+W]
        if np.sqrt((s**2).mean()) < 5e-4: continue
        s = s - s.mean()
        f, p = yin(s)
        if f: out.append((i/SR, f, p))
    return out


def noise_period(x):
    """Match the spectral centroid against what each LFSR period produces."""
    X = np.abs(np.fft.rfft(x * np.hanning(len(x))))**2
    fr = np.fft.rfftfreq(len(x), 1/SR)
    cent = (fr*X).sum()/max(X.sum(), 1e-12)
    from nes_apu import NOISE_PERIOD, CPU
    rates = CPU / NOISE_PERIOD          # LFSR clock rate ~ perceived brightness
    return int(np.argmin(np.abs(rates/3.2 - cent))), cent


def describe(path):
    x = master(load(path))
    if not len(x) or np.abs(x).max() == 0: return None
    tr = track(x)
    if not tr: return None
    ts = np.array([t for t,_,_ in tr]); fs = np.array([f for _,f,_ in tr]); ps = np.array([p for _,_,p in tr])
    good = ps > 0.55
    per = float(np.mean(good))
    e = np.abs(x); third = max(1, len(e)//3)
    a, b = np.sqrt((e[:third]**2).mean()), np.sqrt((e[-third:]**2).mean())
    env = "decay" if b < a*0.5 else ("build" if b > a*1.8 else "steady")
    lo = np.abs(np.fft.rfft(x)); fr = np.fft.rfftfreq(len(x), 1/SR)
    lowfrac = lo[fr < 200].sum()/max(lo.sum(), 1e-12)
    f0 = float(np.median(fs[good])) if good.any() else float(np.median(fs))
    if per < 0.45:                      chan = "noise"
    elif f0 < 200 and lowfrac > 0.35:   chan = "triangle"
    else:                               chan = "pulse"
    npd, cent = noise_period(x)
    return dict(sec=len(x)/SR, periodic=per, f0=f0,
                f0_start=float(np.median(fs[:max(1,len(fs)//3)])),
                f0_end=float(np.median(fs[-max(1,len(fs)//3):])),
                chan=chan, env=env, noise_period=npd, centroid=cent)


if __name__ == "__main__":
    print(f"{'key':<8}{'sec':>6}{'per':>6}{'f0':>7}{'start':>7}{'end':>7}{'cent':>7}{'np':>4}{'chan':>10}  env")
    for f in sorted(glob.glob("01_source-sfx/SFX *.mp3"),
                    key=lambda p: int(re.search(r'\d+', p.split('/')[-1]).group())):
        n = int(re.search(r'\d+', f.split('/')[-1]).group())
        d = describe(f)
        if not d: print(f"SFX-{n:02d}   -- silent --"); continue
        print(f"SFX-{n:02d}{d['sec']:>7.2f}{d['periodic']:>6.2f}{d['f0']:>7.0f}"
              f"{d['f0_start']:>7.0f}{d['f0_end']:>7.0f}{d['centroid']:>7.0f}"
              f"{d['noise_period']:>4}{d['chan']:>10}  {d['env']}")
