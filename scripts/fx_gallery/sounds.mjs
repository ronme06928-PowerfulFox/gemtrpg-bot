import settings from '../sound_lab/presets.json' with { type: 'json' };

const t = settings.cue;
export const gemSounds = {
  C1: [{ t, file: 'c1.ogg', gain: 1, rate: 1 }],
  S1: [{ t, file: 's1.ogg', gain: 1, rate: 1 }],
  S2: [{ t, file: 's2.ogg', gain: 1, rate: 1 }],
  S3: [{ t, file: 's3.ogg', gain: 1, rate: 1 }],
};
