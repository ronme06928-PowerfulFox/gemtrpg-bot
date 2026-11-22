/**
 * Read-only forecast batches for the declare panel.
 * - The scope (room, battle, source, target, opponent's skill) decides which rows are valid at all:
 *   changing it clears them.
 * - Any other state change re-checks the rows but keeps showing the previous ones until replaced,
 *   so the badges do not blink.
 * - The selected skill is asked alone first, then the rest in small batches painted as they arrive.
 */
export const ODDS_BATCH = 25;

export class MatchOdds {
  constructor(request, changed, delay=60) {
    this.request=request; this.changed=changed; this.delay=delay;
    this.scope=null; this.key=null; this.rows={}; this.generation=0;
  }
  update(context) {
    const scope=context ? JSON.stringify([context.room,context.battle,context.source,context.target,context.opponent]) : null;
    // Choosing another skill only reorders the asks; the rows already cover it, so it is not a new key.
    const key=context ? JSON.stringify({...context,priority:undefined}) : null;
    if (key===this.key) return;
    this.key=key;
    const generation=++this.generation;
    clearTimeout(this.timer);
    // No context (the panel is hidden or between renders) only pauses: the rows stay for the same scope.
    if (!context) return;
    if (scope!==this.scope) {
      this.scope=scope;
      if (Object.keys(this.rows).length) { this.rows={}; this.changed(); }
    }
    const order=[...new Set([context.priority,...context.skills].filter(Boolean))];
    const batches=[];
    if (context.priority) batches.push(order.splice(0,1));
    for (let i=0; i<order.length; i+=ODDS_BATCH) batches.push(order.slice(i,i+ODDS_BATCH));
    this.timer=setTimeout(async () => {
      for (const skills of batches) {
        if (generation!==this.generation) return;
        let result;
        try {
          result=await this.request({room_id:context.room,battle_id:context.battle,
            slot_id:context.source,target_slot_id:context.target,skill_ids:skills});
        } catch (_) { continue; /* A failed batch keeps its previous badges. */ }
        if (generation!==this.generation) return;
        const rows={...this.rows};
        for (const skill of skills) {
          if (result?.odds?.[skill]) rows[skill]=result.odds[skill]; else delete rows[skill];
        }
        this.rows=rows; this.changed();
      }
    },this.delay);
  }
  clear() {
    const hadRows = Object.keys(this.rows).length > 0;
    this._reset();
    if (hadRows) this.changed();
  }

  destroy() {
    this._reset();
  }

  _reset() {
    clearTimeout(this.timer);
    ++this.generation;
    this.scope = null;
    this.key = null;
    this.rows = {};
  }
}
