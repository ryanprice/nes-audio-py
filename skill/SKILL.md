---
name: nes-audio
description: Generate authentic NES / 8-bit chiptune sound effects and music by synthesizing the Ricoh 2A03 in software, and recreate existing chip audio in the same style without copying it. Use when asked for NES, Famicom, 8-bit, chiptune or retro-game sounds or music; when recreating sound effects or tracks from an NES-era game; or when AI-generated retro audio comes back sounding "too digital".
---

# NES audio: synthesize the chip, don't imitate it

## The one decision that matters

**Do not use a generative audio model for NES sound.** The Ricoh 2A03 is five
fixed voices whose algorithm is fully documented (nesdev.org/wiki/APU). A
diffusion model approximating that hardware sounds wrong in a way listeners
identify instantly as "too digital", and no amount of prompt engineering fixes
it. Run the chip's actual arithmetic instead — it is a few hundred lines, it runs
in about a second per effect on CPU, and it is correct by construction.

`nesaudio/nes_apu.py` is the chip. `nesaudio/nes_tracker.py` is a tracker on top
of it for music. Install with `pip install -e .` from the repo root.

| Channel | What it is | Typical use |
|---|---|---|
| Pulse 1 & 2 | square, 4 duty cycles (12.5/25/50/75%), 4-bit volume, hardware sweep | melody, harmony, whistles, beeps |
| Triangle | 32-step, fixed volume, no envelope | bass, low thuds |
| Noise | 15-bit LFSR, 16 periods, white or short "metallic" mode | drums, impacts, crowd |
| DMC | 1-bit delta samples | rare, expensive in ROM |

Mixing is **non-linear** — `mix()` implements the hardware formula. Channels
compress against each other; summing them linearly sounds wrong.

## The frame table is the texture

**A sound driver rewrites the registers once per video frame (60.0988 Hz NTSC)
and the chip holds each value until the next write.** Nothing is interpolated.
That staircase is most of what makes chip audio sound alive.

Smooth parameter curves are the single commonest mistake. Build per-frame tables
and step-hold them (`hold`, `seq_pulse`, `seq_triangle`, `seq_noise`). Measure it:
energy in the 6–80 Hz band of the amplitude envelope, 12 ms smoothing so the
carrier cannot leak in. On one real effect: original 25.8k, smooth curves 15.4k,
frame tables 24–31k.

Rate and depth are separate knobs. One rebuild matched the original's 15 Hz
modulation rate while still measuring less than half its texture, because the
retrigger only dipped to 8/15. Taking it to 3/15 fixed it.

## Recreating existing chip audio

Keep the rhythmic shape — that is the texture. Change the pitch content — that is
what makes the result yours. Two dials at once: transpose the root, **and** scale
the semitone contour around it, so intervals differ rather than the line just
sliding up.

**Sound effects and music need different treatment.** Transposing a 0.2 s blip
produces a genuinely new sound. Transposing a 48 s piece does not — the melody is
the authorship, so a transposed copy is still a copy. For music, extract the
*style* (tempo, key, register balance, form, onset density) and compose into it.

## Analysis: measure the structure you intend to reproduce

`nesaudio/analyse_src.py` for effects, `nesaudio/analyse_music.py` for tracks.

- **Use YIN, not plain autocorrelation.** Autocorrelation octave-errors badly on
  short, band-limited chip audio — it pinned 12 of 22 effects to the search
  ceiling.
- **A single-f0 tracker cannot see a two-voice texture.** One effect took three
  rejected rounds before analysing for *two simultaneous non-harmonic partials*
  revealed what it was: a rock-steady drone plus a second voice moving above it.
  Every summary statistic had passed the wrong build.
- **Always check the double tempo.** Autocorrelation scored 91 BPM at +0.78 and
  182 at +0.63 on a ska-punk track; 91 is the bar rate and 182 the pulse. Taking
  the stronger peak produced a march. Onset density settles it — 7.7 strong
  onsets/sec is eighths at 182, not quarters at 91.
- **Never use a ratio of means whose denominator can cross zero.** An offbeat
  ratio swung between +23 and −3 on near-identical mixes. Use a bounded share,
  `off/(off+down)`.

## Verify, don't trust

Adapt the checks in `nesaudio/master_verify.py`: SILENT, CLIPPED, TOO-SHORT,
LATE-ATTACK, MULTI-EVENT (hysteresis: arm above 60% of peak, re-arm below 25%),
plus a band-split comparison against the reference. **Always render the amplitude
envelope** — ASCII is enough. Summary statistics cannot see repeats: a file with
two pops has the same span, trend and spectrum as one with a single pop.

**Trust the band split over the centroid.** One build measured *brighter* than its
reference (centroid 1017 vs 718 Hz) yet was rejected for sounding too low — it
carried twice the sub-200 Hz weight, 0.15 vs 0.08. A boomy tail under a thin body
reads as low.

Useful target: keep total band drift (|Δlow| + |Δmid| + |Δhigh|, split at 200 Hz
and 2 kHz) between **0.03 and 0.30** — close enough to read as the same family,
far enough to be a new sound.

## Practical notes

- **NES chips have almost no sub-bass.** Real 2A03 effects are mid-dominant —
  one measured 85% of its energy in 200–2000 Hz. If a fundamental or a repeating
  figure dips below 200 Hz it will read as boomy.
- **Duty choice is tone shaping.** 12.5% spreads energy over eight harmonics and
  thins the body; 50% has a strong fundamental and no second harmonic. Pick by
  where the reference keeps its energy.
- **Long tracks need chunked rendering.** 48 s at the CPU clock is 86 M samples
  per channel. Render in ~2 s chunks and carry each channel's phase across the
  boundary (`frame0`/`phase0`, returned end state) or you get clicks at the seams.
- **Don't use `resample_poly` for CPU→44.1 kHz.** 1789773/44100 needs a ~1.2 M-tap
  polyphase filter; fine for a 1 s effect, hopeless for a track. `decimate()`
  low-passes once at 18 kHz and interpolates — O(n), and it is the anti-alias
  filter, not the resampler, that stops a square wave folding back.
- Peak-normalise to −1 dBFS, never loudness-normalise: SFX live on transients.

## Try it without installing

`web/index.html` is a self-contained browser playground — the same chip ported
to JavaScript, with presets, live parameters and WAV export. It also prints the
equivalent Python for whatever you dial in.

## Examples

`examples/effects.py` — six one-shots, one per channel technique.
`examples/song.py` — eight bars on all four channels.
