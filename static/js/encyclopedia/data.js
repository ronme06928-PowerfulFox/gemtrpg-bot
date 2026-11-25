(function () {
  const buffBooks = [
    ['能力の増減', '盛衰', 'emerald'], ['状態異常の強化', '傷痕', 'kyanite'],
    ['特殊スタック', '蓄積', 'sunstone'], ['出身の恩恵', '故郷', 'jade'],
    ['物語', '伝承', 'zircon'], ['', '雑録', 'smoky'],
  ];
  function buffVolumes(rows) {
    return buffBooks.map(([category, title, color], index) => ({
      key:`buff-${index}`, kind:'buff', title, color,
      rows:rows.filter(row => (row.data.category || '') === category),
    })).filter(book => book.rows.length);
  }
  async function load({ room, signal } = {}) {
    const kinds = ['glossary', 'skill', 'buff', 'item', 'radiance', 'passive'];
    const url = '/api/encyclopedia' + (room ? '?room=' + encodeURIComponent(room) : '');
    const masters = kinds.map(kind => `/api/get_${kind}_data` + (kind === 'passive' && room ? '?room=' + encodeURIComponent(room) : ''));
    const responses = await Promise.all([url, ...masters].map(async path => {
      const response = await fetchWithSession(path, { signal, cache:'no-cache' });
      if (!response.ok) throw new Error('図鑑を読み込めませんでした。接続とログインを確認してください。');
      return response.json();
    }));
    return { masters:Object.fromEntries(kinds.map((kind, index) => [kind, responses[index + 1]])), extra:responses[0] };
  }
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
          && (full || row.payload.domain !== 'hollow')
          && (full || row.visibility === 'public' || encounters.has('unit:' + row.entry_id)))
          .map(row => [row.entry_id, row.payload])
        : Object.entries(masters[kind] || {});
      const rows = entries.filter(([id, data]) => !data.deprecated && !id.startsWith('SYS-')).map(([id, data]) => {
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
  window.EncyclopediaData = { build, buffVolumes, load };
})();
