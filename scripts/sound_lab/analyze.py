"""Estimate onsets and modes in overlapping chimes from a short recording."""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks, stft


RATE = 48_000
HOP = 96
DEFAULT_SECONDS = 4.05


def decode(path, start, seconds, channels=1):
    raw = subprocess.check_output([
        'ffmpeg', '-v', 'error', '-ss', str(start), '-i', str(path), '-t', str(seconds),
        '-f', 'f32le', '-ac', str(channels), '-ar', str(RATE), '-threads', '1', '-',
    ])
    return np.frombuffer(raw, dtype='<f4').reshape(-1, channels)


def fft_peaks(audio, onset):
    center = round(onset * RATE)
    width = 1536
    before = np.pad(audio[max(0, center - width):center], (max(0, width - center), 0))
    after = audio[center:center + width]
    if len(after) < width:
        return []
    window = np.hanning(width)
    delta = abs(np.fft.rfft(after * window, 8192)) - 0.85 * abs(np.fft.rfft(before * window, 8192))
    hz = np.fft.rfftfreq(8192, 1 / RATE)
    return [(float(hz[i]), float(delta[i])) for i in find_peaks(delta)[0]
            if 500 <= hz[i] <= 15_000 and delta[i] > 0]


def estimate_decay(magnitude, hz, times, frequency, onset, stop):
    band = abs(hz - frequency) <= 55
    if not band.any():
        return None
    power = np.linalg.norm(magnitude[band], axis=0)
    window = np.flatnonzero((onset + .014 <= times) & (times < stop))
    if len(window) < 15:
        return None
    prefix = power[(onset - .06 < times) & (times < onset - .025)]
    floor = float(np.median(prefix)) if len(prefix) else 0
    peak = int(np.argmax(power[window]))
    window = window[peak:]
    if len(window) < 12 or power[window[0]] <= floor * 1.25:
        return None
    db = 20 * np.log10(np.maximum(power[window] - floor, max(1e-8, power[window[0]] * .04)))
    slope, _ = np.polyfit(times[window], db, 1)
    return round(float(-20 / slope), 3) if -600 < slope < -12 else None


def analyze(audio, start=0):
    audio = np.asarray(audio)
    if len(audio) < 4096:
        raise ValueError('At least 0.086 seconds of audio are required')
    hz, times, z = stft(audio, RATE, nperseg=2048, noverlap=2048 - HOP)
    magnitude = abs(z)
    power = magnitude ** 2
    total = power.sum(axis=0)
    peaks = np.log1p(magnitude[(hz >= 6_000) & (hz <= 15_000)] * 1_200)
    flux = np.r_[0, np.maximum(np.diff(peaks, axis=1), 0).mean(axis=0)]
    prominence = max(.003, np.percentile(flux, 95) * .62)
    indices = find_peaks(flux, prominence=prominence, distance=round(.024 * RATE / HOP))[0]
    hits = []
    for index in indices:
        onset = float(times[index])
        if total[index] < total.max() * .0005:
            continue
        candidates = fft_peaks(audio, onset)
        low = [peak for peak in candidates if 1_700 <= peak[0] < 6_300]
        if not low:
            low = [peak for peak in candidates if peak[0] < 7_000]
        if not low:
            continue
        freq, strength = max(low, key=lambda peak: peak[1])
        high = [peak for peak in candidates if 1.55 <= peak[0] / freq <= 3.35]
        overtone, overtone_strength = max(high, key=lambda peak: peak[1], default=(None, 0))
        if overtone_strength < strength * .20:
            overtone = None
        hits.append({
            't': round(onset + start, 3), 'freq': round(freq, 1),
            'ratio': round(overtone / freq, 3) if overtone else None,
            'relative_amplitude': round(overtone_strength / strength, 3) if overtone else None,
            'strength': round(strength, 3),
            'fundamental_t20': estimate_decay(magnitude, hz, times, freq, onset, onset + .23),
            'overtone_t20': estimate_decay(magnitude, hz, times, overtone, onset, onset + .17) if overtone else None,
        })

    level = np.sqrt(total)
    centroid = (hz[:, None] * power).sum(axis=0) / np.maximum(total, 1e-16)
    weights = total[total > 0]
    active = times <= len(audio) / RATE
    shape = []
    for edge in np.arange(0, len(audio) / RATE, .20):
        mask = (times >= edge) & (times < edge + .20) & active
        rms = float(np.sqrt(np.mean(total[mask])))
        shape.append({'t': round(float(edge) + start, 2), 'relative_db': round(20 * np.log10(max(1e-8, rms / max(level.max(), 1e-8))), 1)})
    intervals = [round(b['t'] - a['t'], 3) for a, b in zip(hits, hits[1:])]

    def median(values):
        values = [value for value in values if value is not None]
        return round(float(np.median(values)), 3) if values else None

    return {'start': start, 'seconds': round(len(audio) / RATE, 5), 'hits': hits, 'intervals': intervals,
            'level': shape, 'summary': {'hit_count': len(hits), 'median_gap': median(intervals),
                'centroid_hz': round(float((centroid * total).sum() / max(weights.sum(), 1e-16)), 1),
                'ratio': median(bar['ratio'] for bar in hits),
                'fundamental_t20': median(bar['fundamental_t20'] for bar in hits),
                'overtone_t20': median(bar['overtone_t20'] for bar in hits)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--seconds', type=float, default=DEFAULT_SECONDS)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    report = analyze(decode(args.input, args.start, args.seconds)[:, 0], args.start)
    if args.compare:
        comparison = analyze(decode(args.compare, 0, args.seconds)[:, 0])
        report = {str(path): {'intervals': item['intervals'], **item['summary']}
                  for path, item in ((args.input, report), (args.compare, comparison))}
    payload = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding='utf-8')
    else:
        print(payload, end='')


if __name__ == '__main__':
    main()
