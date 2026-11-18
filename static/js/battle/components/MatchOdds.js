/** Read-only forecast batches. Every state change invalidates outstanding replies. */
export class MatchOdds {
  constructor(request, changed, delay=160) {
    this.request=request; this.changed=changed; this.delay=delay;
    this.key=null; this.rows={}; this.generation=0;
  }
  update(context) {
    const key=context ? JSON.stringify(context) : null;
    if (key===this.key) return;
    this.key=key; this.rows={}; const generation=++this.generation;
    clearTimeout(this.timer);
    if (!context) return;
    this.timer=setTimeout(async () => {
      const rows={};
      for (let i=0; i<context.skills.length; i+=100) {
        if (generation!==this.generation) return;
        try {
          const result=await this.request({room_id:context.room,battle_id:context.battle,
            slot_id:context.source,target_slot_id:context.target,skill_ids:context.skills.slice(i,i+100)});
          if (generation!==this.generation) return;
          Object.assign(rows,result.odds || {});
        } catch (_) { /* Missing replies leave only this batch without badges. */ }
      }
      if (generation!==this.generation) return;
      this.rows=rows; this.changed();
    },this.delay);
  }
  destroy() { clearTimeout(this.timer); ++this.generation; this.key=null; this.rows={}; }
}
