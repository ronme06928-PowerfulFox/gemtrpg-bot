export const defaultAuditionVolume = 0.55;

export function createAuditionAudio(assets) {
  let context, master;
  let volume = defaultAuditionVolume;
  const active = new Set();
  const pending = new Map();
  const buffers = new Map();

  function unlock(notes) {
    if (!context) {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) return;
      context = new Audio();
      master = context.createGain();
      master.gain.setValueAtTime(volume, context.currentTime);
      master.connect(context.destination);
    }
    const tasks = [];
    if (context.state !== 'running') tasks.push(context.resume());
    for (const { file } of notes) {
      if (!assets[file] || buffers.has(file)) continue;
      if (!pending.has(file)) {
        const bytes = Uint8Array.from(atob(assets[file].split(',')[1]), character => character.charCodeAt(0));
        pending.set(file, context.decodeAudioData(bytes.buffer).then(buffer => buffers.set(file, buffer))
          .finally(() => pending.delete(file)));
      }
      tasks.push(pending.get(file));
    }
    if (tasks.length) return Promise.all(tasks);
  }

  function stop() {
    for (const source of active) source.stop();
    active.clear();
  }

  function schedule(notes, elapsed, scale) {
    if (context?.state !== 'running') return 0;
    const now = context.currentTime;
    let end = 0;
    for (const { t, file, gain, rate } of notes) {
      const delay = t * scale - elapsed;
      // 同じ時刻を指定した場合は、浮動小数点の丸め差で飛ばさない。
      if (delay < -1e-9 || !buffers.has(file)) continue;
      const source = context.createBufferSource();
      source.buffer = buffers.get(file);
      source.playbackRate.value = rate;
      end = Math.max(end, t * scale + source.buffer.duration / rate);
      const level = context.createGain();
      const start = now + Math.max(0, delay);
      level.gain.setValueAtTime(gain, start);
      source.connect(level);
      level.connect(master);
      source.onended = () => {
        active.delete(source);
        source.disconnect();
        level.disconnect();
      };
      active.add(source);
      source.start(start);
    }
    return end;
  }

  return { unlock, schedule, stop, setVolume(value) {
    volume = value;
    if (master) master.gain.setValueAtTime(volume, context.currentTime);
  } };
}
