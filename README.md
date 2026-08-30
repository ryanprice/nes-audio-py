# nesaudio

A **Ricoh 2A03** — the NES sound chip — running in numpy. Not a chiptune
*emulation* or a set of samples: the actual hardware algorithm, at the real
1.789773 MHz NTSC clock, decimated to 44.1 kHz.

```python
from nesaudio import nes_apu as a

def whistle(n):
    p = a.pulse(n, [(0, 1900), (.35, 2400), (1, 2500)], duty=0,
                vol=[(0, 15), (.55, 13), (1, 0)])
    return a.mix(p1=p, n=n)

audio = a.render(0.45, whistle)     # -> float array at 44.1 kHz
```

No GPU, no model, no network. About a second per sound effect.

**[Try it in the browser →](https://ryanprice.github.io/nes-audio-py/)** — the same
chip ported to JavaScript, with presets, live parameters, WAV export, and the
equivalent Python printed for whatever you dial in. Nothing to install.

## Why not just use a generative audio model

Because the 2A03 is five fixed voices with published arithmetic. A diffusion
model approximating it produces something listeners immediately identify as
"too digital", and no amount of prompting fixes it — the failure is structural.
Running the real algorithm is correct by construction, faster, and reproducible.

This library exists because that lesson was learned the expensive way.

## The chip

| Channel | What it is | Typical use |
|---|---|---|
| Pulse 1 & 2 | square, 4 duty cycles (12.5/25/50/75%), 4-bit volume, hardware sweep | melody, harmony, whistles, beeps |
| Triangle | 32-step, fixed volume, no envelope | bass, low thuds |
| Noise | 15-bit LFSR, 16 periods, white or short "metallic" mode | drums, impacts, crowd |

Mixing is **non-linear** — `mix()` implements the hardware formula, so channels
compress against each other the way they do on real hardware. Summing them
linearly sounds wrong.

## The frame table is the texture

This is the part that matters most, and the part that is easy to miss.

**A NES sound driver rewrites the chip's registers once per video frame
(60.0988 Hz) and the chip holds each value until the next write.** Nothing is
interpolated. That staircase is most of what makes chip audio sound alive.

Smooth parameter curves are the commonest mistake. Use the `seq_*` functions,
which take per-frame tables:

```python
import numpy as np
from nesaudio import nes_apu as a

def coin(n):
    hz  = np.array([988] * 6 + [1319] * 24)              # two held pitches
    vol = np.concatenate([np.full(6, 14.), np.linspace(14, 0, 24)])
    return a.mix(p1=a.seq_pulse(n, hz, vol, duty=1), n=n)
```

Measure it as energy in the 6–80 Hz band of the amplitude envelope (12 ms
smoothing, so the carrier cannot leak in). On one real effect: 25.8k for the
original, 15.4k with smooth curves, 24–31k with frame tables.

Rate and depth are separate knobs. One rebuild matched the original's 15 Hz
modulation rate while still measuring less than half its texture, because the
retrigger only dipped to 8/15 rather than 3/15.

## Music

`nes_tracker` is a small tracker on top of the chip — notes and pattern rows in,
per-frame tables out. `examples/song.py` is eight bars on four channels.

```python
from nesaudio import nes_tracker as t

tracks = dict(
    p1  = t.line(LEAD,  fpr=5, vol=13, decay=0.6),
    p2  = t.line(SKANK, fpr=5, vol=13, decay=2.2),
    tri = t.line(BASS,  fpr=5, vol=15),
    noi = t.drums(BEAT, fpr=5),
)
audio = t.render(tracks, fpr=5, duties={"p1": 2, "p2": 0})
```

Rows are `"C5"` for a new note, `"-"` to sustain, `"."` to rest. `fpr` is video
frames per row; at 16th-note rows, `fpr=5` gives 180 BPM and `fpr=10` gives 90.

Long tracks render in ~2 s chunks with each channel's phase carried across the
boundary, so a three-minute piece never holds more than a couple of seconds of
CPU-rate audio in memory and has no clicks at the seams.

## Analysis

`analyse_src` (effects) and `analyse_music` (tracks) recover what a piece of
existing chip audio is doing — channel, pitch, envelope, tempo, key, form — so
you can rebuild in the same style. Four things learned the hard way:

- **Use YIN, not plain autocorrelation.** Autocorrelation octave-errors badly on
  short band-limited chip audio; it pinned 12 of 22 effects to the search ceiling.
- **A single-f0 tracker cannot see a two-voice texture.** One effect took three
  rejected rebuilds before analysing for two simultaneous non-harmonic partials
  revealed it was a steady drone plus a moving upper voice.
- **Always check the double tempo.** Autocorrelation scored 91 BPM at +0.78 and
  182 at +0.63 on a ska-punk track — 91 is the bar rate, 182 the pulse. Onset
  density settles it: 7.7 strong onsets/sec is eighths at 182, not quarters at 91.
- **Never use a ratio of means whose denominator can cross zero.** An offbeat
  metric swung between +23 and −3 on near-identical mixes. Use a bounded share.

## Verification

`master_verify` has the checks: SILENT, CLIPPED, TOO-SHORT, LATE-ATTACK and
MULTI-EVENT (hysteresis — arm above 60% of peak, re-arm below 25%), plus
band-split comparison and an ASCII envelope renderer.

**Always render the envelope.** Summary statistics cannot see repeats: a file
with two pops has the same span, trend and spectrum as one with a single pop.

**Trust the band split over the centroid.** One build measured *brighter* than
its reference (centroid 1017 vs 718 Hz) yet was rejected for sounding too low —
it carried twice the sub-200 Hz weight. A boomy tail under a thin body reads as
low. Real 2A03 effects are mid-dominant; one measured 85% of its energy in
200–2000 Hz.

## Two gotchas that cost real time

**Don't use `resample_poly` for CPU → 44.1 kHz.** 1789773/44100 needs a ~1.2 M-tap
polyphase filter. Fine for a one-second effect, hopeless for a track — it didn't
finish in two minutes. `decimate()` low-passes once at 18 kHz and interpolates:
O(n), and it's the anti-alias filter, not the resampler, that stops a square wave
folding back as inharmonic tones.

**Don't write mono as stereo with ffmpeg `-ac 2`.** Its upmix applies a −3 dB pan
law, so audio peak-normalised to −1 dBFS lands on disk at −4. Silent, consistent,
and invisible unless you measure it. `write()` uses an explicit unity-gain `pan`.

## Use it from an agent

`skill/` holds a [Claude Code](https://claude.com/claude-code) skill that teaches
an agent this library *and* the traps that make chip audio come out wrong:

```bash
mkdir -p ~/.claude/skills/nes-audio && cp skill/SKILL.md ~/.claude/skills/nes-audio/
```

It then loads whenever you ask for NES, Famicom, 8-bit or chiptune audio — or
when AI-generated retro audio comes back sounding "too digital", which is the
situation it was written for.

## Install

```bash
git clone https://github.com/ryanprice/nes-audio-py
cd nes-audio-py
pip install -e .

python examples/effects.py    # six one-shots
python examples/song.py       # eight bars of chip music
```

The browser playground needs no install, but ES modules will not load from
`file://` — serve the folder:

```bash
cd docs && python -m http.server 8000     # then open localhost:8000
```

Requires Python 3.10+, numpy and scipy.

## Reference

[nesdev.org/wiki/APU](https://www.nesdev.org/wiki/APU) — the hardware
documentation everything here is built from.

## License

MIT
