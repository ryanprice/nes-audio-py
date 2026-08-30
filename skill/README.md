# The `nes-audio` skill

A [Claude Code](https://claude.com/claude-code) skill that teaches an agent to
use this library — and, more importantly, the traps that make chip audio come
out wrong.

## Install

```bash
mkdir -p ~/.claude/skills/nes-audio
cp SKILL.md ~/.claude/skills/nes-audio/
```

Then ask for NES, Famicom, 8-bit or chiptune audio and it loads automatically.
It also triggers when AI-generated retro audio comes back sounding "too
digital", which is the situation it was written for.

## What it carries

The method — synthesize the 2A03 rather than generate it, build per-frame
register tables rather than smooth curves, keep the rhythmic shape and change
the pitch content when recreating existing audio — plus the analysis gotchas
(YIN over autocorrelation, check the double tempo, analyse for two partials when
you hear two voices) and the verification checks.
