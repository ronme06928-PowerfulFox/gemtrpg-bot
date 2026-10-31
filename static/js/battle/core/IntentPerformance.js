// Disabled by default. Measurements stay in this page's memory.
export class IntentPerformance {
  constructor(options = {}) {
    this.now = options.now || (() => performance.now());
    this.visible = options.visible || (() => typeof document === 'undefined' || document.visibilityState === 'visible');
    this.frame = options.frame || globalThis.requestAnimationFrame?.bind(globalThis);
    this.cancelFrame = options.cancelFrame || globalThis.cancelAnimationFrame?.bind(globalThis);
    this.setTimer = options.setTimer || ((callback, delay) => globalThis.setTimeout(callback, delay));
    this.clearTimer = options.clearTimer || ((timer) => globalThis.clearTimeout(timer));
    this.sequence = 0;
    this.makeId = options.makeId || (() => globalThis.crypto?.randomUUID?.() || `intent-${Date.now().toString(36)}-${++this.sequence}`);
    this.enabled = false;
    this.pending = new Map();
    this.samples = [];
    this.active = null;
  }

  start() {
    this.clear();
    this.enabled = true;
  }

  stop() {
    this.enabled = false;
    this._discardPending();
    return this.report();
  }

  clear() {
    this._discardPending();
    this.samples = [];
  }

  _discardPending() {
    for (const record of this.pending.values()) this._cleanup(record);
    this.pending.clear();
  }

  _cleanup(record) {
    this.clearTimer(record.timer);
    if (record.frame != null) this.cancelFrame?.(record.frame);
  }

  report() {
    return {
      enabled: this.enabled,
      pending: this.pending.size,
      samples: this.samples.map((sample) => ({ ...sample, stages_ms: { ...sample.stages_ms } })),
    };
  }

  emit(socket, event, payload) {
    if (!this.enabled || !socket.connected || this.pending.size >= 50) {
      socket.emit(event, payload);
      return;
    }
    const id = this.makeId();
    const record = {
      id, event, sent: this.now(), transport: socket.io?.engine?.transport?.name || 'unknown',
      ack: null, received: null, store: null, panel: 0, frameMs: null, frameStatus: 'pending', stages: {},
    };
    this.pending.set(id, record);
    record.timer = this.setTimer(() => this._finish(record, 'timeout'), 8000);
    socket.emit(event, { ...payload, _intent_perf_id: id }, (response) => {
      if (!this.pending.has(id)) return;
      record.ack = this.now();
      const timing = response?.intent_perf;
      if (timing?.id !== id || !Number.isFinite(timing.handler_ms) || timing.handler_ms < 0) {
        this._finish(record, 'server_unavailable');
        return;
      }
      record.server = timing.handler_ms;
      for (const key of ['redirect_ms', 'ready_ms', 'delivery_ms']) {
        if (Number.isFinite(timing.stages_ms?.[key]) && timing.stages_ms[key] >= 0) record.stages[key] = timing.stages_ms[key];
      }
      if (!timing.state_emitted) this._finish(record, 'no_state_emitted');
      else this._complete(record);
    });
  }

  receive(payload, apply) {
    const record = this.pending.get(payload?._intent_perf?.id);
    if (!record || record.received !== null) return apply();
    record.received = this.now();
    const previous = this.active;
    this.active = record;
    try {
      apply();
    } finally {
      record.store = this.now() - record.received;
      this.active = previous;
    }
    if (!this.visible()) record.frameStatus = 'hidden';
    else if (!this.frame) record.frameStatus = 'unavailable';
    else {
      record.frame = this.frame(() => {
        if (!this.pending.has(record.id)) return;
        if (!this.visible()) {
          record.frameStatus = 'hidden';
          this._complete(record);
          return;
        }
        record.frame = this.frame(() => {
          if (!this.pending.has(record.id)) return;
          record.frameStatus = this.visible() ? 'observed' : 'hidden';
          if (record.frameStatus === 'observed') record.frameMs = this.now() - record.received;
          this._complete(record);
        });
      });
    }
    this._complete(record);
  }

  render(callback) {
    const record = this.active;
    if (!record) return callback();
    const started = this.now();
    try {
      return callback();
    } finally {
      record.panel += this.now() - started;
    }
  }

  _complete(record) {
    if (record.ack !== null && record.received !== null && record.frameStatus !== 'pending') {
      this._finish(record, 'complete');
    }
  }

  _finish(record, status) {
    if (!this.pending.delete(record.id)) return;
    this._cleanup(record);
    const rtt = record.ack === null ? null : record.ack - record.sent;
    this.samples.push({
      event: record.event, transport: record.transport, status,
      rtt_ms: rtt, server_ms: record.server ?? null,
      remaining_rtt_ms: rtt !== null && record.server != null ? rtt - record.server : null,
      send_to_state_ms: record.received === null ? null : record.received - record.sent,
      store_dispatch_ms: record.store, declare_panel_ms: record.received === null ? null : record.panel,
      receive_to_frame_ms: record.frameMs, frame_status: record.frameStatus,
      stages_ms: record.stages,
    });
    if (this.samples.length > 200) this.samples.shift();
  }
}

export const intentPerformance = new IntentPerformance();
if (typeof window !== 'undefined') {
  window.GemDicePerf = {
    start: () => intentPerformance.start(), stop: () => intentPerformance.stop(),
    clear: () => intentPerformance.clear(), report: () => intentPerformance.report(),
  };
}
