// Ricoh 2A03 (NES APU) in JavaScript -- a direct port of nesaudio/nes_apu.py.
// Runs the hardware algorithm at the NTSC CPU clock, then decimates to 44.1 kHz.
// Reference: https://www.nesdev.org/wiki/APU

export const CPU = 1789773.0;
export const SR = 44100;
export const VFRAME = CPU / 60.0988;          // NTSC video frame, in CPU cycles

const DUTY = [
  [0, 1, 0, 0, 0, 0, 0, 0],   // 12.5%
  [0, 1, 1, 0, 0, 0, 0, 0],   // 25%
  [0, 1, 1, 1, 1, 0, 0, 0],   // 50%
  [1, 0, 0, 1, 1, 1, 1, 1],   // 75%
];
const TRI_SEQ = (() => {
  const a = [];
  for (let i = 15; i >= 0; i--) a.push(i);
  for (let i = 0; i < 16; i++) a.push(i);
  return a;
})();
export const NOISE_PERIOD =
  [4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068];

const timer = (hz, chan) => {
  const div = chan === 'pulse' ? 16 : 32;
  if (hz <= 0) return 2047;
  return Math.min(2047, Math.max(0, CPU / (div * hz) - 1));
};

// Curve from [t, value] knots, evaluated at position p in 0..1
function knot(pts, p) {
  if (typeof pts === 'number') return pts;
  if (p <= pts[0][0]) return pts[0][1];
  for (let i = 1; i < pts.length; i++) {
    if (p <= pts[i][0]) {
      const [t0, v0] = pts[i - 1], [t1, v1] = pts[i];
      const f = t1 === t0 ? 0 : (p - t0) / (t1 - t0);
      return v0 + (v1 - v0) * f;
    }
  }
  return pts[pts.length - 1][1];
}

// The 4-bit envelope updates at 240 Hz, so volume is quantised and stepped --
// that granularity is audible and is part of why chip audio is not smooth.
const QUARTER = CPU / 240.0;

export function pulse(n, hzSpec, dutyIdx, volSpec, retrigFrames = 0) {
  const out = new Float32Array(n);
  let phase = 0;
  const seq = DUTY[dutyIdx];
  for (let i = 0; i < n; i++) {
    const p = i / n;
    const f = knot(hzSpec, p);
    phase += 1 / (2 * (timer(f, 'pulse') + 1));
    let v = Math.round(Math.min(15, Math.max(0, knot(volSpec, Math.floor(i / QUARTER) * QUARTER / n))));
    if (retrigFrames > 0) {
      // re-attack every N video frames: the texture lever
      const k = Math.floor(i / VFRAME) % retrigFrames;
      v = Math.round(v * [1, 0.55, 0.35, 0.22, 0.15, 0.1, 0.08, 0.06][Math.min(k, 7)]);
    }
    out[i] = f < 54 ? 0 : seq[Math.floor(phase) & 7] * v;
  }
  return out;
}

export function triangle(n, hzSpec, gateSpec) {
  const out = new Float32Array(n);
  let phase = 0;
  for (let i = 0; i < n; i++) {
    const p = i / n;
    phase += 1 / (timer(knot(hzSpec, p), 'tri') + 1);
    out[i] = knot(gateSpec, p) > 0.5 ? TRI_SEQ[Math.floor(phase) & 31] : 0;
  }
  return out;
}

export function noise(n, periodIdx, volSpec, mode = 0, seed = 1) {
  const out = new Float32Array(n);
  const per = NOISE_PERIOD[Math.min(15, Math.max(0, Math.round(periodIdx)))];
  const tap = mode ? 6 : 1;
  let reg = (seed & 0x7fff) || 1, i = 0;
  while (i < n) {
    const bit = (reg & 1) ? 0 : 1;               // output is the inverse of bit 0
    const fb = (reg ^ (reg >> tap)) & 1;
    reg = (reg >> 1) | (fb << 14);
    const end = Math.min(n, i + per);
    for (; i < end; i++) {
      const v = Math.round(Math.min(15, Math.max(0, knot(volSpec,
        Math.floor(i / QUARTER) * QUARTER / n))));
      out[i] = bit * v;
    }
  }
  return out;
}

// The chip's non-linear mixer: channels do not sum linearly.
export function mix(n, { p1, p2, tri, noi } = {}) {
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const ps = (p1 ? p1[i] : 0) + (p2 ? p2[i] : 0);
    const pulseOut = ps > 0 ? 95.88 / (8128 / ps + 100) : 0;
    const inner = (tri ? tri[i] : 0) / 8227 + (noi ? noi[i] : 0) / 12241;
    const tndOut = inner > 0 ? 159.79 / (1 / inner + 100) : 0;
    out[i] = pulseOut + tndOut;
  }
  return out;
}

// CPU clock -> 44.1 kHz. A rational resampler here needs a ~1.2M-tap filter;
// low-passing once and interpolating is O(n) and inaudibly different, because
// it is the anti-alias filter that stops a square wave folding back.
function lowpass(x, fc, sr, passes = 4) {
  const dt = 1 / sr, rc = 1 / (2 * Math.PI * fc), al = dt / (rc + dt);
  const y = Float32Array.from(x);
  for (let p = 0; p < passes; p++) {
    let prev = y[0];
    for (let i = 1; i < y.length; i++) { prev += al * (y[i] - prev); y[i] = prev; }
  }
  return y;
}

export function render(seconds, build) {
  const n = Math.floor(CPU * seconds);
  let x = build(n);
  let mean = 0;
  for (let i = 0; i < n; i++) mean += x[i];
  mean /= n;
  for (let i = 0; i < n; i++) x[i] -= mean;                 // DC block
  const filt = lowpass(x, 18000, CPU);
  const m = Math.floor(seconds * SR);
  const out = new Float32Array(m);
  const step = CPU / SR;
  for (let i = 0; i < m; i++) {
    const pos = i * step, i0 = Math.floor(pos), f = pos - i0;
    out[i] = filt[i0] * (1 - f) + (filt[i0 + 1] ?? filt[i0]) * f;
  }
  let pk = 0;
  for (let i = 0; i < m; i++) pk = Math.max(pk, Math.abs(out[i]));
  if (pk > 0) { const g = Math.pow(10, -1 / 20) / pk; for (let i = 0; i < m; i++) out[i] *= g; }
  return out;
}

export function toWav(samples, sr = SR) {
  const n = samples.length, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); str(8, 'WAVEfmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, 'data'); v.setUint32(40, n * 2, true);
  for (let i = 0; i < n; i++) v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, samples[i])) * 32767, true);
  return new Blob([buf], { type: 'audio/wav' });
}
