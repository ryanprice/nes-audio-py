#!/usr/bin/env python3
"""Eight bars of chip music: lead, harmony, bass and kit on four channels."""
from nesaudio import nes_tracker as t
from nesaudio.master_verify import write

FPR = 5          # frames per 16th note -> 180 BPM
R, H = ".", "-"


def e(*notes):
    """A bar as eight eighth-notes."""
    out = []
    for n in notes:
        out += [n, H if n not in (R, H) else n]
    return out


LEAD = (e("C5", R, "C5", "Eb5", "G5", R, "Eb5", R) +
        e("D5", R, "C5", "Bb4", "C5", R, R, R) +
        e("Eb5", R, "Eb5", "F5", "G5", R, "F5", R) +
        e("Eb5", R, "D5", "C5", "D5", R, R, R)) * 2
SKANK = (e(R, "Eb4", R, "Eb4", R, "Eb4", R, "Eb4") +
         e(R, "D4", R, "D4", R, "D4", R, "D4") +
         e(R, "G4", R, "G4", R, "G4", R, "G4") +
         e(R, "D4", R, "D4", R, "D4", R, "D4")) * 2
BASS = (e("C2", "C2", "C2", "G2", "C2", "C2", "G2", "C2") +
        e("Bb1", "Bb1", "Bb1", "F2", "Bb1", "Bb1", "F2", "Bb1") +
        e("Eb2", "Eb2", "Eb2", "Bb2", "Eb2", "Eb2", "Bb2", "Eb2") +
        e("G1", "G1", "G1", "D2", "G1", "G1", "D2", "G1")) * 2
BEAT = ["K", R, "H", R, "S", R, "H", R, "K", R, "H", R, "S", R, "H", "K"]
KIT = {"K": (13, 10, 4), "S": (7, 15, 7), "H": (4, 9, 2)}

if __name__ == "__main__":
    tracks = dict(
        p1=t.line(LEAD, FPR, vol=13, decay=0.6),
        p2=t.line(SKANK, FPR, vol=13, decay=2.2),
        tri=t.line(BASS, FPR, vol=15),
        noi=t.drums(BEAT * (len(LEAD) // 16), FPR, kit=KIT),
    )
    y = t.render(tracks, FPR, duties={"p1": 2, "p2": 0})
    write("song.wav", y)
    print(f"wrote song.wav  {len(y)/t.SR:.1f}s")
