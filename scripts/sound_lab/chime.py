"""Render the gem-blessing auditions from values and a fixed random seed."""
import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

from analyze import RATE, decode


ROOT = Path(__file__).resolve().parents[2]
MAX_OGG_BYTES = 60_000


def filter_noise(samples, lower, upper):
    return sosfilt(butter(2, [lower, upper], 'bandpass', fs=RATE, output='sos'), samples)


def fade_and_normalize(samples, fade, peak_dbfs):
    count = min(len(samples), round(fade * RATE))
    if count:
        samples[-count:] *= np.linspace(1, 0, count)[:, None]
    peak = np.max(np.abs(samples))
    return samples * (10 ** (peak_dbfs / 20) / peak) if peak else samples


def strike_bar(bar, config, rng, time, copies):
    jitter = config['jitter']
    strength = bar['gain'] * (config['copy_gain'] if copies else 1)
    strength *= rng.uniform(1 - jitter['gain'], 1 + jitter['gain'])
    if bar['freq'] < config['low_split_hz']:
        strength *= config['low_gain']
    frequency = bar['freq'] * 2 ** (rng.uniform(-jitter['cents'], jitter['cents']) / 1200)
    pan = np.clip(bar['pan'] + rng.uniform(-jitter['pan'], jitter['pan']), -.92, .92)
    positioned = np.array([np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)])
    sample = np.zeros(len(time))
    for index, (ratio, amplitude, decay) in enumerate(zip(bar['ratios'], bar['overtones'], bar['decay'])):
        mode = frequency * ratio
        if mode >= RATE * .46:
            continue
        level = amplitude * (config['overtones'] if index else 1)
        envelope = np.exp(-np.log(10) * time / (decay * config['decay']))
        sample += level * envelope * np.sin(2 * np.pi * mode * time + rng.uniform(0, 2 * np.pi))
    sample *= np.minimum(1, time / .0012)
    strike = config['strike']
    count = round(strike['seconds'] * RATE)
    noise = filter_noise(rng.standard_normal(count), *strike['band_hz']) * np.hanning(count)
    count = min(count, len(sample))
    sample[:count] += noise[:count] * strike['gain']
    return sample[:, None] * positioned * strength


def render(settings, name):
    variant = settings['variants'][name]
    config = {**settings['defaults'], **variant}
    rng = np.random.default_rng(settings['seed'])
    audio = np.zeros((round(config['duration'] * RATE), 2))
    time = np.arange(len(audio)) / RATE
    peak_time = settings['peak_time']
    time_scale = (settings['flash'] - settings['cue']) / peak_time if config['align_peak'] else 1
    for bar in settings['bars']:
        if bar['t'] and bar['freq'] < config['min_hz']:
            continue
        copies = config['copies'] if bar['freq'] >= config['low_split_hz'] else 0
        for copy in range(copies + 1):
            jitter_t = rng.uniform(-config['jitter']['time'], config['jitter']['time'])
            if copy == 0 and bar['t'] in (0, peak_time):
                jitter_t = 0
            elif copy:
                jitter_t += copy * config['copy_gap']
            beginning = max(0, round((bar['t'] * time_scale + jitter_t) * RATE))
            if beginning < len(time):
                audio[beginning:] += strike_bar(bar, config, rng, time[:len(time) - beginning], copy)

    tone = butter(2, config['cutoff_hz'], 'lowpass', fs=RATE, output='sos')
    audio = sosfilt(tone, audio, axis=0)
    wet = config['reverb']
    tail = np.arange(round(wet['seconds'] * RATE)) / RATE
    noise = rng.standard_normal((len(tail), 2))
    impulse = sosfilt(butter(2, wet['cutoff_hz'], 'lowpass', fs=RATE, output='sos'), noise, axis=0)
    impulse *= (np.exp(-6.9 * tail / wet['seconds']) * np.minimum(1, tail / .018))[:, None]
    impulse /= np.linalg.norm(impulse, axis=0)
    reflection = fftconvolve(audio, impulse, axes=0)[:len(audio)]
    audio = audio * (1 - wet['mix']) + reflection * wet['mix']
    return fade_and_normalize(audio, config['fade'], settings['peak_dbfs'])


def write_ogg(audio, path):
    data = subprocess.check_output([
        'ffmpeg', '-v', 'error', '-f', 'f32le', '-ar', str(RATE), '-ac', '2', '-i', '-',
        '-map_metadata', '-1', '-c:a', 'libvorbis', '-q:a', '3', '-fflags', '+bitexact',
        '-flags:a', '+bitexact', '-threads', '1', '-f', 'ogg', '-',
    ], input=audio.astype('<f4').tobytes())
    if len(data) > MAX_OGG_BYTES:
        raise ValueError(f'{path.name}: {len(data)} bytes exceed {MAX_OGG_BYTES}')
    path.write_bytes(data)
    print(f'{path.name}: {len(data):,} bytes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, default=Path(__file__).with_name('presets.json'))
    parser.add_argument('--output-dir', type=Path, default=ROOT / '_local/sound_lab')
    parser.add_argument('--reference', type=Path, default=ROOT / '_local/sound_sources/c1_preview.mp3')
    args = parser.parse_args()
    settings = json.loads(args.settings.read_text(encoding='utf-8'))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name in settings['variants']:
        write_ogg(render(settings, name), args.output_dir / f'{name}.ogg')
    if args.reference.is_file():
        cut = settings['reference']
        audio = decode(args.reference, cut['start'], cut['duration'], channels=2).copy()
        audio[:240] *= np.linspace(0, 1, 240)[:, None]
        write_ogg(fade_and_normalize(audio, cut['fade'], settings['peak_dbfs']), args.output_dir / 'c1.ogg')
    else:
        (args.output_dir / 'c1.ogg').unlink(missing_ok=True)
        print('C1 preview unavailable; rendered S1-S3.')


if __name__ == '__main__':
    main()
