(function () {
  // 推薦ピン（計画35 PR35-18）。ホストとオーナー以外が、決め待ちの札にピンを立てる。
  const esc = value => window.CatalogWorkspaceParts.h(value ?? '');
  const COLORS = ['#6fb8e8', '#e06a8a', '#7fcf7f', '#e0a040', '#b48cf0', '#f0d27a', '#8fd0ff', '#ef9a4a'];

  // 参加した順で色を割り当てる（8人までは重ならない）。
  function colorFor(state, id) {
    const index = (state.hollow?.members || []).findIndex(member => member.id === id);
    return COLORS[Math.max(0, index) % COLORS.length];
  }

  const pinners = state => (state.hollow?.members || [])
    .filter(member => member.id !== state.hollow.host_user_id && member.role !== 'owner');
  const byUser = state => state.hollow?.run?.pins?.by_user || {};

  function canPin(state) {
    return !!currentUserId && !!state.hollow?.run?.pins?.scene && pinners(state).some(member => member.id === currentUserId);
  }

  function marks(state, option) {
    const pins = byUser(state);
    const users = Object.keys(pins).filter(id => pins[id] === option);
    if (!users.length) return '';
    const name = id => state.hollow.members?.find(member => member.id === id)?.name || '—';
    const names = users.map(name).join('・');
    return `<span class="hollow-pins" title="ピン：${esc(names)}" aria-label="ピン：${esc(names)}">${users.map(id =>
      `<i class="${id === currentUserId ? 'is-mine' : ''}" style="--pin:${colorFor(state, id)}" aria-hidden="true">${esc(Array.from(name(id))[0])}</i>`).join('')}</span>`;
  }

  const attrs = (state, option) => `data-pin="${esc(option)}" aria-pressed="${byUser(state)[currentUserId] === option}"`;

  function hint(state, manage) {
    const people = pinners(state).length;
    if (!people || !state.hollow?.run?.pins?.scene) return '';
    const tally = `ピン ${Object.keys(byUser(state)).length} / ${people}人`;
    return manage ? tally : `札を押すとピンを立てる（もう一度で外す）· ${tally} · 決めるのはホスト`;
  }

  window.HollowPins = {canPin, marks, attrs, hint};
})();
