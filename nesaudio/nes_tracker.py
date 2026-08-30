#!/usr/bin/env python3
"""A minimal NES tracker over the 2A03: notes and patterns in, frame tables out.

Renders in chunks with channel phase carried across boundaries, so a
three-minute track never holds more than a couple of seconds of CPU-rate audio
in memory and still has no clicks at the seams.
"""
import numpy as np
from . import nes_apu as a
from scipy.signal import butter, sosfilt

SR = 44100
NAMES = {"C":0,"C#":1,"Db":1,"D":2,"D#":3,"Eb":3,"E":4,"F":5,"F#":6,"Gb":6,
         "G":7,"G#":8,"Ab":8,"A":9,"A#":10,"Bb":10,"B":11}


def hz(note):
    """'C4' -> Hz. A4 = 440."""
    if note in (None, "", "-", "."):
        return 0.0
    i = 2 if len(note) > 2 and note[1] in "#b" else 1
    return 440.0 * 2 ** ((NAMES[note[:i]] + 12*(int(note[i:]) + 1) - 69) / 12.0)


def line(seq, fpr, vol=12, decay=0.0, legato=False):
    """Expand a row list into per-frame (hz, vol) tables.

    Rows: 'C4' a new note, '-' sustain, '.' or None a rest.
    `decay` sheds that many volume steps per frame after each attack, which is
    how a driver fakes an envelope the pulse channel does not have.
    """
    H, V = [], []
    cur, curv = 0.0, 0.0
    for row in seq:
        if row in (None, ".", ""):
            cur, curv = (cur, 0.0) if legato else (0.0, 0.0)
        elif row == "-":
            pass
        else:
            cur = hz(row); curv = float(vol)
        for k in range(fpr):
            H.append(cur)
            V.append(max(0.0, curv - decay*k) if cur else 0.0)
    return np.array(H), np.array(V)


def drums(seq, fpr, kit=None):
    """Rows: 'K' kick, 'S' snare, 'H' hat, '.' rest. Values are (period, vol, len)."""
    kit = kit or {"K": (13, 15, 5), "S": (8, 15, 6), "H": (4, 8, 2)}
    P, V = [], []
    for row in seq:
        hit = kit.get(row)
        for k in range(fpr):
            if hit and k < hit[2]:
                P.append(hit[0]); V.append(max(0.0, hit[1] - 3.0*k))
            else:
                P.append(kit["H"][0]); V.append(0.0)
    return np.array(P), np.array(V)


def render(tracks, fpr, chunk_sec=2.0, duties=None):
    """tracks: dict with p1/p2/tri/noi -> (table_a, table_b). Returns 44.1k audio."""
    duties = duties or {}
    F = max(len(t[0]) for t in tracks.values())
    for k, (x, y) in tracks.items():
        if len(x) < F:
            tracks[k] = (np.pad(x, (0, F-len(x)), mode="edge"),
                         np.pad(y, (0, F-len(y))))
    total = F * a.VFRAME
    st = {"p1": 0.0, "p2": 0.0, "tri": 0.0, "noi": 1}
    out, done, frame0, zi = [], 0.0, 0, None
    while done < total:
        n = int(min(chunk_sec * a.CPU, total - done))
        if n <= 0:
            break
        ntot = n
        ch = {}
        if "p1" in tracks:
            h, v = tracks["p1"]
            ch["p1"], st["p1"] = a.seq_pulse(ntot, h, v, duties.get("p1", 1),
                                             frame0, st["p1"], state=True)
        if "p2" in tracks:
            h, v = tracks["p2"]
            ch["p2"], st["p2"] = a.seq_pulse(ntot, h, v, duties.get("p2", 0),
                                             frame0, st["p2"], state=True)
        if "tri" in tracks:
            h, g = tracks["tri"]
            ch["tri"], st["tri"] = a.seq_triangle(ntot, h, g, frame0, st["tri"], state=True)
        if "noi" in tracks:
            p, v = tracks["noi"]
            ch["noi"], st["noi"] = a.seq_noise(ntot, p, v, seed=st["noi"],
                                               frame0=frame0, state=True)
        mixed = a.mix(p1=ch.get("p1"), p2=ch.get("p2"), tri=ch.get("tri"),
                      noi=ch.get("noi"), n=ntot)
        y, zi = a.decimate(mixed, zi)
        out.append(y)
        done += n
        frame0 += n / a.VFRAME
    y = np.concatenate(out)
    y = y - y.mean()
    y = sosfilt(butter(1, 30.0, "hp", fs=SR, output="sos"), y)
    pk = np.abs(y).max()
    return (y / pk * 10 ** (-1.0/20)) if pk > 0 else y
