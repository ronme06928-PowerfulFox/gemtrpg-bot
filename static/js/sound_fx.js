/* static/js/sound_fx.js */

(function () {
    if (typeof window === 'undefined') return;
    if (window.SoundFx) return;

    const STORAGE_KEYS = {
        enabled: 'sound_fx_enabled',
        volume: 'sound_fx_volume',
        diceSources: 'sound_fx_dice_sources'
    };

    const DEFAULT_DICE_SOURCES = [
        '/static/audio/dice-roll.mp3'
    ];
    const LEGACY_DEFAULT_DICE_SOURCES = new Set([
        '/audio/dice-roll.mp3',
        '/audio/dice-roll.ogg',
        '/audio/dice-roll.wav',
        '/static/audio/dice-roll.mp3',
        '/static/audio/dice-roll.ogg',
        '/static/audio/dice-roll.wav',
        'audio/dice-roll.mp3',
        'audio/dice-roll.ogg',
        'audio/dice-roll.wav',
        'static/audio/dice-roll.mp3',
        'static/audio/dice-roll.ogg',
        'static/audio/dice-roll.wav'
    ]);

    const MIN_INTERVAL_MS = 90;
    const MAX_TRACKED_LOG_KEYS = 2500;
    const PRUNE_TARGET = 1800;
    const POOL_SIZE_PER_SOURCE = 2;

    const playedLogKeys = new Set();
    let lastSignature = '';
    let lastSignatureAt = 0;
    let lastPlayAt = 0;
    let preferredSourceIndex = 0;
    let warnedNoSource = false;
    let sourceUnavailable = false;
    let unlocked = false;
    let unlockListenerAttached = false;
    let audioContext = null;
    let lastFailure = null;
    const sourceAudioPool = new Map();

    let enabled = loadBool(STORAGE_KEYS.enabled, true);
    let volume = clamp(loadNumber(STORAGE_KEYS.volume, 0.55), 0, 1);
    let diceSources = normalizeSourceList(loadArray(STORAGE_KEYS.diceSources, DEFAULT_DICE_SOURCES));
    persist(STORAGE_KEYS.diceSources, JSON.stringify(diceSources));

    function loadBool(key, fallback) {
        try {
            const raw = localStorage.getItem(key);
            if (raw === null) return fallback;
            return raw === '1' || raw === 'true';
        } catch (_e) {
            return fallback;
        }
    }

    function loadNumber(key, fallback) {
        try {
            const raw = localStorage.getItem(key);
            const n = Number(raw);
            return Number.isFinite(n) ? n : fallback;
        } catch (_e) {
            return fallback;
        }
    }

    function loadArray(key, fallback) {
        try {
            const raw = localStorage.getItem(key);
            if (!raw) return fallback.slice();
            const parsed = JSON.parse(raw);
            if (!Array.isArray(parsed)) return fallback.slice();
            return parsed;
        } catch (_e) {
            return fallback.slice();
        }
    }

    function persist(key, value) {
        try {
            localStorage.setItem(key, value);
        } catch (_e) {
            // ignore localStorage errors
        }
    }

    function clamp(n, min, max) {
        return Math.max(min, Math.min(max, n));
    }

    function normalizeSourceList(value) {
        const raw = Array.isArray(value) ? value : [value];
        const seen = new Set();
        const out = [];
        raw.forEach((v) => {
            const s = String(v || '').trim();
            if (!s || seen.has(s)) return;
            seen.add(s);
            out.push(s);
        });
        if (out.length <= 0) return DEFAULT_DICE_SOURCES.slice();
        const isLegacyOnly = out.every((src) => LEGACY_DEFAULT_DICE_SOURCES.has(src));
        if (isLegacyOnly) return DEFAULT_DICE_SOURCES.slice();
        return out;
    }

    function attachUnlockListeners() {
        if (unlockListenerAttached) return;
        unlockListenerAttached = true;
        const unlock = () => {
            unlocked = true;
            warmupSources();
            void ensureAudioContextReady(true);
        };
        const opts = { capture: true, passive: true, once: true };
        window.addEventListener('pointerdown', unlock, opts);
        window.addEventListener('keydown', unlock, opts);
        window.addEventListener('touchstart', unlock, opts);
    }

    function prunePlayedLogKeys() {
        if (playedLogKeys.size <= MAX_TRACKED_LOG_KEYS) return;
        const keep = Array.from(playedLogKeys).slice(-PRUNE_TARGET);
        playedLogKeys.clear();
        keep.forEach((k) => playedLogKeys.add(k));
    }

    function buildLogKey(logData) {
        const hasId = (logData && logData.log_id !== undefined && logData.log_id !== null);
        if (hasId) {
            const id = String(logData.log_id);
            const hasTs = (logData.timestamp !== undefined && logData.timestamp !== null);
            return hasTs ? `${id}:${String(logData.timestamp)}` : id;
        }
        return '';
    }

    function alreadyPlayed(logData) {
        const key = buildLogKey(logData);
        if (key) {
            if (playedLogKeys.has(key)) return true;
            playedLogKeys.add(key);
            prunePlayedLogKeys();
            return false;
        }

        const sig = `${String(logData?.type || '')}|${String(logData?.user || '')}|${String(logData?.message || '')}`;
        const now = Date.now();
        const duplicated = (sig === lastSignature && (now - lastSignatureAt) < 400);
        lastSignature = sig;
        lastSignatureAt = now;
        return duplicated;
    }

    function isDiceLikeChat(message) {
        const text = String(message || '');
        if (!/\d+d\d+/i.test(text)) return false;
        return /(?:=|->)/.test(text);
    }

    function isDiceLog(logData) {
        const type = String(logData?.type || '').toLowerCase();
        if (type === 'dice' || type === 'dice_roll') return true;
        if (type === 'chat' && isDiceLikeChat(logData?.message)) return true;
        return false;
    }

    function effectiveVolume() {
        const v = clamp(Number(volume), 0, 1);
        if (v <= 0) return 0.55;
        return v;
    }

    function parseError(err) {
        return {
            name: String(err?.name || ''),
            message: String(err?.message || '')
        };
    }

    function resetSourceHealth() {
        sourceUnavailable = false;
        warnedNoSource = false;
    }

    function sourceList() {
        const raw = normalizeSourceList(diceSources);
        if (raw.length <= 0) return DEFAULT_DICE_SOURCES.slice();
        return raw;
    }

    function createPooledAudio(src) {
        const audio = new Audio(src);
        audio.preload = 'auto';
        audio.volume = effectiveVolume();
        audio.playsInline = true;
        try {
            audio.load();
        } catch (_e) {
            // Ignore warmup/load errors.
        }
        return audio;
    }

    function ensureSourcePool(src) {
        const key = String(src || '').trim();
        if (!key) return [];
        let pool = sourceAudioPool.get(key);
        if (!Array.isArray(pool)) {
            pool = [];
            sourceAudioPool.set(key, pool);
        }
        if (pool.length <= 0) {
            for (let i = 0; i < POOL_SIZE_PER_SOURCE; i += 1) {
                pool.push(createPooledAudio(key));
            }
        }
        return pool;
    }

    function updateAllPoolVolumes() {
        sourceAudioPool.forEach((pool) => {
            if (!Array.isArray(pool)) return;
            pool.forEach((audio) => {
                if (!audio) return;
                audio.volume = effectiveVolume();
            });
        });
    }

    function warmupSources() {
        const sources = sourceList();
        sources.forEach((src) => {
            const pool = ensureSourcePool(src);
            pool.forEach((audio) => {
                if (!audio) return;
                try {
                    audio.load();
                } catch (_e) {
                    // Ignore warmup/load errors.
                }
            });
        });
    }

    async function playHtmlAudio(src) {
        const pool = ensureSourcePool(src);
        let audio = pool.find((a) => !!a && (a.paused || a.ended));
        if (!audio) {
            audio = createPooledAudio(src);
            pool.push(audio);
        }
        audio.volume = effectiveVolume();
        try {
            if (!audio.paused) audio.pause();
            audio.currentTime = 0;
        } catch (_e) {
            // Ignore seek/reset errors.
        }
        await audio.play();
        return true;
    }

    async function playFromSources() {
        const sources = sourceList();
        const total = sources.length;
        if (total === 0) return { ok: false, blocked: false, failures: [] };

        const failures = [];
        let blocked = false;

        for (let step = 0; step < total; step += 1) {
            const idx = (preferredSourceIndex + step) % total;
            const src = String(sources[idx] || '').trim();
            if (!src) continue;

            try {
                await playHtmlAudio(src);
                preferredSourceIndex = idx;
                return { ok: true, blocked: false, source: src, failures };
            } catch (err) {
                const parsed = parseError(err);
                if (parsed.name === 'NotAllowedError') blocked = true;
                failures.push({ src, ...parsed });
            }
        }

        return { ok: false, blocked, failures };
    }

    async function ensureAudioContextReady(force) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return false;
        if (!audioContext) {
            try {
                audioContext = new Ctx();
            } catch (_e) {
                return false;
            }
        }
        if (audioContext.state === 'running') return true;
        if (!force && !unlocked) return false;
        try {
            await audioContext.resume();
            return audioContext.state === 'running';
        } catch (_e) {
            return false;
        }
    }

    async function playFallbackTone(options = {}) {
        const opts = options || {};
        const ready = await ensureAudioContextReady(Boolean(opts.force));
        if (!ready || !audioContext) return false;

        const now = audioContext.currentTime;
        const gain = audioContext.createGain();
        const oscA = audioContext.createOscillator();
        const oscB = audioContext.createOscillator();

        oscA.type = 'triangle';
        oscB.type = 'square';
        oscA.frequency.setValueAtTime(680, now);
        oscB.frequency.setValueAtTime(1120, now);

        const g = Math.max(0.02, Math.min(0.22, effectiveVolume() * 0.32));
        gain.gain.setValueAtTime(0.0001, now);
        gain.gain.exponentialRampToValueAtTime(g, now + 0.01);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.14);

        oscA.connect(gain);
        oscB.connect(gain);
        gain.connect(audioContext.destination);

        oscA.start(now);
        oscB.start(now);
        oscA.stop(now + 0.14);
        oscB.stop(now + 0.12);

        return true;
    }

    async function playDiceRoll(options = {}) {
        const opts = options || {};
        const force = Boolean(opts.force);

        if (!enabled && !force) return false;
        if (!unlocked && !force) return false;

        const now = Date.now();
        const bypassThrottle = Boolean(opts.bypassThrottle || force);
        if (!bypassThrottle && (now - lastPlayAt) < MIN_INTERVAL_MS) return false;
        lastPlayAt = now;

        const result = await playFromSources();
        if (result.ok) {
            resetSourceHealth();
            lastFailure = null;
            return true;
        }

        lastFailure = {
            at: now,
            blocked: Boolean(result.blocked),
            failures: Array.isArray(result.failures) ? result.failures.slice(0, 8) : []
        };

        if (!result.blocked) {
            sourceUnavailable = true;
            if (!warnedNoSource) {
                warnedNoSource = true;
                console.warn('[SoundFx] Dice SE source failed. Check /audio/dice-roll.* or configure SoundFx.setDiceSource(path).');
            }
        }

        const allowFallback = (opts.allowFallback !== false);
        if (allowFallback) {
            const fallbackOk = await playFallbackTone({ force });
            if (fallbackOk) return true;
        }

        return false;
    }

    function maybePlayForLog(logData) {
        if (!logData || typeof logData !== 'object') return false;
        if (!isDiceLog(logData)) return false;
        if (alreadyPlayed(logData)) return false;
        void playDiceRoll();
        return true;
    }

    function setEnabled(value) {
        enabled = Boolean(value);
        persist(STORAGE_KEYS.enabled, enabled ? '1' : '0');
        return enabled;
    }

    function setVolume(value) {
        const parsed = Number(value);
        if (Number.isFinite(parsed)) {
            volume = clamp(parsed, 0, 1);
            persist(STORAGE_KEYS.volume, String(volume));
            updateAllPoolVolumes();
        }
        return volume;
    }

    function setDiceSources(value) {
        const cleaned = normalizeSourceList(value);
        diceSources = cleaned;
        preferredSourceIndex = 0;
        resetSourceHealth();
        sourceAudioPool.clear();
        warmupSources();
        persist(STORAGE_KEYS.diceSources, JSON.stringify(diceSources));
        return diceSources.slice();
    }

    function getSettings() {
        return {
            enabled,
            volume,
            diceSources: sourceList(),
            unlocked,
            sourceUnavailable,
            lastFailure: lastFailure ? { ...lastFailure } : null
        };
    }

    function configure(options = {}) {
        if (options.enabled !== undefined) setEnabled(options.enabled);
        if (options.volume !== undefined) setVolume(options.volume);
        if (options.diceSrc !== undefined) setDiceSources([options.diceSrc]);
        if (options.diceSources !== undefined) setDiceSources(options.diceSources);
        return getSettings();
    }

    function unlock() {
        unlocked = true;
        warmupSources();
        void ensureAudioContextReady(true);
        return unlocked;
    }

    function resetFailures() {
        lastFailure = null;
        resetSourceHealth();
        return true;
    }

    attachUnlockListeners();
    warmupSources();

    window.SoundFx = {
        configure,
        getSettings,
        setEnabled,
        setVolume,
        setDiceSources,
        setDiceSource: (src) => setDiceSources([src]),
        unlock,
        resetFailures,
        playDiceRoll,
        maybePlayForLog
    };
})();
