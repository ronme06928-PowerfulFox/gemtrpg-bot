(function () {
  const types = [
    ['glossary', '用語'], ['skill', 'スキル'], ['buff', 'バフ'], ['item', 'アイテム'],
    ['enemy', 'エネミー'], ['radiance', '輝化スキル'], ['passive', '特殊パッシブ'],
  ];
  function build(masters, extra, ownEncounters) {
    const full = extra.can_view_all && !ownEncounters;
    const encounters = new Map(extra.encounters.map(row => [row.kind + ':' + row.entry_id, row.first_seen_at]));
    const groups = window.CatalogSkill.groups.flatMap(([category, entries]) =>
      entries.map(([prefix, title]) => [prefix, title, category]));
    const ranks = new Map(groups.map(([prefix], index) => [prefix, index]));
    const rowsByKind = Object.fromEntries(types.map(([kind]) => {
      const entries = kind === 'enemy'
        ? extra.units.filter(row => row.payload.allow_enemy !== false
          && (full || row.visibility === 'public' || encounters.has('unit:' + row.entry_id)))
          .map(row => [row.entry_id, row.payload])
        : Object.entries(masters[kind] || {});
      const rows = entries.filter(([id, data]) => !data.deprecated && !id.startsWith('SYS-')
        && (full || !data.marks?.includes('hollow'))).map(([id, data]) => {
        const gated = kind === 'enemy' || (kind === 'skill' && id.startsWith('E-'))
          || (['passive', 'buff', 'item'].includes(kind) && data.marks?.includes('enemy'));
        const firstSeenAt = encounters.get((kind === 'enemy' ? 'unit' : kind) + ':' + id);
        return {
          id, kind, data, gated, firstSeenAt,
          name: data.display_name || data.デフォルト名称 || data.name || id,
          met: !!(full || !gated || firstSeenAt || data.marks?.includes('known')),
        };
      });
      rows.sort((a, b) => (kind === 'skill'
        ? (ranks.get(a.id.split('-')[0]) ?? ranks.size) - (ranks.get(b.id.split('-')[0]) ?? ranks.size) : 0)
        || a.id.localeCompare(b.id, 'en', { numeric: true }));
      return [kind, rows];
    }));
    return { types, groups, rowsByKind, markLabels:extra.mark_labels };
  }
  window.EncyclopediaData = { build };
})();
