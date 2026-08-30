#!/usr/bin/env python3
"""Six one-shot effects, showing each channel and the frame-table idea."""
import numpy as np
from nesaudio import nes_apu as a
from nesaudio.master_verify import write


def whistle(n):
    """Pulse channel, rising, thin duty -- a referee's whistle."""
    p = a.pulse(n, [(0, 1900), (.35, 2400), (1, 2500)], duty=0,
                vol=[(0, 15), (.55, 13), (1, 0)])
    return a.mix(p1=p, n=n)


def tackle(n):
    """Two noise layers at different LFSR periods -- an impact."""
    return a.mix(noi=a.noise(n, period=6, vol=[(0, 15), (.25, 11), (1, 0)])
                     + a.noise(n, period=10, vol=[(0, 0), (.3, 11), (1, 0)], seed=0x2A03),
                 n=n)


def thud(n):
    """Triangle for weight, noise for the attack."""
    return a.mix(tri=a.triangle(n, [(0, 74), (1, 52)], vol=[(0, 1), (.85, 1), (1, 0)]),
                 noi=a.noise(n, period=11, vol=[(0, 9), (.3, 2), (1, 0)]), n=n)


def beep(n):
    return a.mix(p1=a.pulse(n, 520, duty=3, vol=[(0, 15), (.35, 11), (1, 0)]), n=n)


def coin(n):
    """A frame table, not a curve: two held pitches, stepped."""
    hz = np.array([988] * 6 + [1319] * 24)
    vol = np.concatenate([np.full(6, 14.0), np.linspace(14, 0, 24)])
    return a.mix(p1=a.seq_pulse(n, hz, vol, duty=1), n=n)


def score(n):
    """Arpeggio retriggered every 4 frames -- the retrigger is the texture."""
    steps = np.array([1.0, 1.19, 1.5, 2.0, 2.52, 3.0])
    hz = np.repeat(659 * steps, 8)
    vol = np.array([15, 8, 5, 3] * 12)[:len(hz)] * np.linspace(1, .2, len(hz)) ** 1.2
    return a.mix(p1=a.seq_pulse(n, hz, vol, duty=1), n=n)


if __name__ == "__main__":
    for name, fn, sec in [("whistle", whistle, .45), ("tackle", tackle, .25),
                          ("thud", thud, .15), ("beep", beep, .25),
                          ("coin", coin, .5), ("score", score, .8)]:
        write(f"{name}.wav", a.render(sec, fn))
        print("wrote", f"{name}.wav")
