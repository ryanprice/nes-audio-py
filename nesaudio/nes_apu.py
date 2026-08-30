#!/usr/bin/env python3
"""Ricoh 2A03 (NES APU) software synthesizer.

Runs the actual hardware algorithm -- duty sequencers, the 15-bit noise LFSR,
the 32-step triangle, 4-bit envelopes and the chip's non-linear mixer -- at the
NTSC CPU clock, then decimates to 44.1 kHz. Nothing here is an imitation of NES
sound; it is the same arithmetic the chip does.

Reference: nesdev.org/wiki/APU
"""
import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi

CPU = 1789773.0          # NTSC CPU clock, Hz
SR = 44100
FRAME = CPU / 240.0      # quarter-frame: envelopes clock at 240 Hz
VFRAME = CPU / 60.0988   # NTSC video frame -- when a sound driver writes registers

# Duty sequences for the pulse channels (nesdev: 12.5 / 25 / 50 / 75 %)
DUTY = np.array([
    [0, 1, 0, 0, 0, 0, 0, 0],
    [0, 1, 1, 0, 0, 0, 0, 0],
    [0, 1, 1, 1, 1, 0, 0, 0],
    [1, 0, 0, 1, 1, 1, 1, 1],
], dtype=np.float64)

# 32-step triangle sequence: 15..0, 0..15
TRI_SEQ = np.concatenate([np.arange(15, -1, -1), np.arange(0, 16)]).astype(np.float64)

# Noise timer periods, in CPU cycles (NTSC)
NOISE_PERIOD = np.array([4, 8, 16, 32, 64, 96, 128, 160,
                         202, 254, 380, 508, 762, 1016, 2034, 4068])


def hold(table, n, frame0=0):
    """Step-hold a per-video-frame table across n CPU cycles.

    A NES sound driver writes the sound registers once per video frame and the
    chip holds that value until the next write. Nothing is interpolated, and
    that staircase is audible -- it is most of the texture in a real NES effect.
    Smooth curves are what make a synthesized chip sound lifeless.
    """
    t = np.asarray(table, dtype=np.float64)
    idx = np.minimum(((np.arange(n) + frame0 * VFRAME) / VFRAME).astype(np.int64),
                     len(t) - 1)
    return t[idx]


def seq_pulse(n, hz_tab, vol_tab, duty=2, frame0=0, phase0=0.0, state=False):
    """Pulse channel driven by per-frame register tables.

    `frame0` and `phase0` let a long track render in chunks: pass the previous
    chunk's returned phase so the sequencer does not restart and click."""
    f = hold(hz_tab, n, frame0)
    t = _timer_from_hz(f, "pulse")
    step = phase0 + np.cumsum(1.0 / (2.0 * (t + 1.0)))
    d = (hold(duty, n, frame0).astype(np.int64) if not np.isscalar(duty)
         else np.full(n, duty, np.int64))
    seq = DUTY[d, (step.astype(np.int64)) & 7]
    out = seq * np.round(np.clip(hold(vol_tab, n, frame0), 0, 15))
    out[f < 54.0] = 0.0
    return (out, float(step[-1] % 8)) if state else out


def seq_triangle(n, hz_tab, gate_tab, frame0=0, phase0=0.0, state=False):
    """Triangle channel driven by per-frame tables. The chip gives the triangle
    no volume control, so `gate_tab` only switches it on or off per frame --
    which is exactly how a driver silences it."""
    f = hold(hz_tab, n, frame0)
    t = _timer_from_hz(f, "tri")
    step = phase0 + np.cumsum(1.0 / (t + 1.0))
    out = TRI_SEQ[(step.astype(np.int64)) & 31] * (hold(gate_tab, n, frame0) > 0.5)
    return (out, float(step[-1] % 32)) if state else out


def seq_noise(n, per_tab, vol_tab, mode=0, seed=1, frame0=0, state=False):
    """Noise channel driven by per-frame tables. The period can change each
    frame, which is how NES drivers get sweeping / chattering noise."""
    per = np.clip(np.round(hold(per_tab, n, frame0)).astype(int), 0, 15)
    reg = int(seed) & 0x7FFF or 1
    tap = 6 if mode else 1
    out = np.empty(n)
    i = 0
    bit = 0.0
    while i < n:
        p = int(NOISE_PERIOD[per[i]])
        bit = 0.0 if (reg & 1) else 1.0
        fb = (reg ^ (reg >> tap)) & 1
        reg = (reg >> 1) | (fb << 14)
        out[i:i+p] = bit
        i += p
    out = out * np.round(np.clip(hold(vol_tab, n, frame0), 0, 15))
    return (out, reg) if state else out


def _timer_from_hz(hz, chan):
    """Invert the hardware frequency formula to an 11-bit timer value."""
    div = 16.0 if chan == "pulse" else 32.0
    f = np.asarray(hz, dtype=np.float64)
    t = np.divide(CPU, div * f, out=np.full_like(f, 2047.0), where=f > 0) - 1.0
    return np.clip(t, 0, 2047)


def _ramp(spec, n):
    """A per-CPU-cycle curve from a scalar or a list of (position, value) knots."""
    if np.isscalar(spec):
        return np.full(n, float(spec))
    pts = np.asarray(spec, dtype=np.float64)
    return np.interp(np.linspace(0, 1, n), pts[:, 0], pts[:, 1])


def _env(spec, n, steps=True):
    """Volume curve. The chip's envelope is 4-bit and updates at 240 Hz, so the
    output is quantised and stepped -- that granularity is audible and is a big
    part of why real NES audio does not sound smooth."""
    v = _ramp(spec, n)
    if not steps:
        return np.clip(v, 0, 15)
    blk = max(1, int(FRAME))
    idx = np.minimum((np.arange(n) // blk) * blk, n - 1)
    return np.round(np.clip(v[idx], 0, 15))


def pulse(n, hz, duty=2, vol=15, sweep=None):
    """Square-wave channel. `hz` and `vol` accept knot lists for glides/decays.
    `sweep` is a semitone offset curve applied on top of `hz`."""
    f = _ramp(hz, n)
    if sweep is not None:
        f = f * 2.0 ** (_ramp(sweep, n) / 12.0)
    t = _timer_from_hz(f, "pulse")
    step = np.cumsum(1.0 / (2.0 * (t + 1.0)))      # sequencer advances every 2(t+1) CPU cycles
    seq = DUTY[duty][(step.astype(np.int64)) & 7]
    v = _env(vol, n)
    out = seq * v
    out[f < 54.0] = 0.0                             # timer < 8: channel is silenced
    return out


def triangle(n, hz, vol=1.0):
    """Triangle channel. Real hardware has no volume control -- `vol` is a gate
    (0 or 1) here, matching how games actually silence it."""
    f = _ramp(hz, n)
    t = _timer_from_hz(f, "tri")
    step = np.cumsum(1.0 / (t + 1.0))               # advances every (t+1) CPU cycles
    out = TRI_SEQ[(step.astype(np.int64)) & 31]
    return out * (_ramp(vol, n) > 0.5)


def noise(n, period=6, vol=15, mode=0, seed=1):
    """Noise channel: 15-bit LFSR, tap bit 1 (white) or bit 6 (short, metallic).
    `period` indexes the hardware period table, 0 = highest pitch."""
    per = int(NOISE_PERIOD[int(np.clip(period, 0, 15))])
    m = n // per + 2
    reg = int(seed) & 0x7FFF or 1
    bits = np.empty(m, dtype=np.float64)
    tap = 6 if mode else 1
    for i in range(m):
        bits[i] = 0.0 if (reg & 1) else 1.0          # output is the inverse of bit 0
        fb = (reg ^ (reg >> tap)) & 1
        reg = (reg >> 1) | (fb << 14)
    out = np.repeat(bits, per)[:n]
    return out * _env(vol, n)


def mix(p1=None, p2=None, tri=None, noi=None, dmc=None, n=None):
    """The 2A03's non-linear mixer. The channels do not sum linearly -- this
    formula is why NES audio compresses the way it does when channels stack."""
    z = np.zeros(n)
    p1 = z if p1 is None else p1
    p2 = z if p2 is None else p2
    tri = z if tri is None else tri
    noi = z if noi is None else noi
    dmc = z if dmc is None else dmc
    ps = p1 + p2
    pulse_out = np.where(ps > 0, 95.88 / np.where(ps > 0, 8128.0 / np.where(ps > 0, ps, 1) + 100.0, 1), 0.0)
    inner = tri / 8227.0 + noi / 12241.0 + dmc / 22638.0
    tnd_out = np.where(inner > 0, 159.79 / (1.0 / np.where(inner > 0, inner, 1) + 100.0), 0.0)
    return pulse_out + tnd_out


ANTIALIAS = butter(8, 18000.0, "lp", fs=CPU, output="sos")


def decimate(x, zi=None):
    """CPU clock -> 44.1 kHz: low-pass, then sample at the target positions.

    A rational resampler for 1789773/44100 needs a ~1.2M-tap polyphase filter,
    which is far too slow for a full-length track. Filtering once and
    interpolating is O(n) and inaudibly different here, because the anti-alias
    filter -- not the interpolation -- is what stops a square wave folding back
    as inharmonic tones. `zi` carries filter state across chunks.
    """
    if zi is None:
        zi = sosfilt_zi(ANTIALIAS) * x[0]
    y, zi = sosfilt(ANTIALIAS, x, zi=zi)
    m = int(len(x) / CPU * SR)
    pos = np.arange(m) * (CPU / SR)
    return np.interp(pos, np.arange(len(y)), y), zi


def render(seconds, build, dc_block=True):
    """Run `build(n)` at the CPU clock and decimate to 44.1 kHz."""
    n = int(CPU * seconds)
    x = build(n)
    x = x - x.mean() if dc_block else x
    y, _ = decimate(x)
    y = sosfilt(butter(1, 30.0, "hp", fs=SR, output="sos"), y)  # chip DC blocking
    pk = np.abs(y).max()
    return (y / pk * 10 ** (-1.0 / 20)) if pk > 0 else y
