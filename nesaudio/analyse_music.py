"""Extract the STYLE of a NES track: tempo, key, harmonic movement, register
layout and form. Deliberately not a transcription -- we want the character to
compose a new piece with, not the tune itself."""
import numpy as np
from .master_verify import load, SR

NOTES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
HOP = 512


def stft(x, n=2048, hop=HOP):
    w = np.hanning(n)
    frames = 1 + (len(x)-n)//hop
    S = np.empty((n//2+1, frames))
    for i in range(frames):
        S[:, i] = np.abs(np.fft.rfft(x[i*hop:i*hop+n]*w))
    return S, np.fft.rfftfreq(n, 1/SR)


def tempo(S):
    flux = np.maximum(0, np.diff(S, axis=1)).sum(0)
    flux = (flux - flux.mean())/ (flux.std() or 1)
    ac = np.correlate(flux, flux, 'full')[len(flux)-1:]
    fps = SR/HOP
    lo, hi = int(fps*60/220), int(fps*60/60)          # 60-220 BPM
    k = lo + int(np.argmax(ac[lo:hi]))
    return 60*fps/k, flux


def chroma(S, fr):
    C = np.zeros(12)
    band = (fr > 60) & (fr < 4000)
    for f, mag in zip(fr[band], S[band].sum(1)):
        C[int(round(12*np.log2(f/440.0))) % 12] += mag
    return C/C.max()


def key_of(C):
    # Krumhansl major/minor profiles
    maj = np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
    mnr = np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])
    best=(None,-9)
    for i in range(12):
        for nm,prof in (("major",maj),("minor",mnr)):
            r = np.corrcoef(np.roll(C,-i), prof)[0,1]
            if r>best[1]: best=((NOTES[i],nm),r)
    return best


def register(S, fr):
    tot = S.sum()
    return {"bass <250Hz": S[fr<250].sum()/tot,
            "mid 250-1k":  S[(fr>=250)&(fr<1000)].sum()/tot,
            "lead 1k-4k":  S[(fr>=1000)&(fr<4000)].sum()/tot,
            "air >4k":     S[fr>=4000].sum()/tot}


def sections(S, n=8):
    """Coarse form: where the texture changes most."""
    F = S/ (S.sum(0)+1e-9)
    step = F.shape[1]//60
    red = np.array([F[:, i*step:(i+1)*step].mean(1) for i in range(60)])
    d = np.array([np.linalg.norm(red[i]-red[i-1]) for i in range(1, 60)])
    return np.argsort(d)[-n:]


if __name__ == "__main__":
    path = sys.argv[1]
    x = load(path)
    S, fr = stft(x)
    bpm, flux = tempo(S)
    C = chroma(S, fr)
    (root, mode), conf = key_of(C)
    print(f"{path}\n  length {len(x)/SR:.1f}s   tempo ~{bpm:.0f} BPM   "
          f"key {root} {mode} (fit {conf:.2f})")
    print("  register balance: " + "  ".join(f"{k} {v:.2f}" for k,v in register(S,fr).items()))
    order = np.argsort(C)[::-1][:7]
    print("  strongest pitch classes: " + " ".join(f"{NOTES[i]}({C[i]:.2f})" for i in order))
    b = sorted(sections(S))
    print("  section changes near: " + ", ".join(f"{i*len(x)/SR/60:.0f}s" for i in b))
