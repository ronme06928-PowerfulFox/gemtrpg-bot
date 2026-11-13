// PR60-22 の試作：未対応の効果のリクエスト（本番には入らない）。
// 本物の管理画面に、見出しのボタン・リクエストの場面・効果の節の入口を重ねる。データは画面の中だけに持つ。
(function () {
  const h = window.CatalogGlossary.escape;
  const as = new URLSearchParams(location.search).get('as') === 'author' ? 'author' : 'admin';
  const me = as === 'admin' ? '管理者' : 'あやめ';
  const STATES = ['受付', '対応中', '実装済み', '見送り'];
  let schemas = {}, nextId = 4, filter = 'open', selectedId = 1, backup = null, form = null;
  const requests = [
    { id: 1, title: '相手の手番を1つ遅らせる', want: '的中時に、相手の次の行動を1つ後ろへずらしたい。速度値を下げるのではなく、順番そのものを入れ替える。', example: '(的中時):対象の次の行動順を1つ遅らせる。', near: 'SCHEDULE_EFFECT', draft: { kind: 'skill', id: 'Ps-04', name: '乱斬' }, state: '受付', by: 'あやめ', at: '2026-11-12', memo: '' },
    { id: 2, title: '与えたダメージの半分だけFPを回復', want: '与えたダメージに比例して自分のFPを回復したい。DRAIN_HP のFP版。', example: '(的中時):与えたダメージの半分（切り捨て）だけFPを回復する。', near: 'DRAIN_HP', draft: null, state: '対応中', by: '管理者', at: '2026-11-10', memo: 'DRAIN_HP に回復先（HP・FP・MP）を足す形で作る予定。' },
    { id: 3, title: '味方全員の出血を1ずつ移す', want: '味方の出血を自分へ集める。', example: '(使用時):味方全員の出血を1ずつ自分へ移す。', near: '', draft: { kind: 'buff', id: 'Bu-20', name: '献身' }, state: '見送り', by: 'あやめ', at: '2026-11-05', memo: '今の状態異常の移し替えはルール側で未定のため見送り。ルールが決まったら出し直してください。' },
  ];
  const open = row => row.state === '受付' || row.state === '対応中';
  const typeLabel = key => schemas.effect_types?.[key]?.label || key;

  // 効果のスキーマを、本物の画面が読むときに横取りして持つ。
  const baseSchemas = window.CatalogApi.effectSchemas;
  window.CatalogApi.effectSchemas = () => baseSchemas().then(value => (schemas = value, value));
  baseSchemas().then(value => { schemas = value; });

  function badge(state) { return `<span class="cat-badge cat-request-state" data-request-state="${h(state)}">${h(state)}</span>`; }
  function headerButton() {
    const holder = document.querySelector('.bo-workspace__header-actions');
    if (!holder) return;
    let slot = holder.querySelector('#cat-request-action');
    if (!slot) { slot = document.createElement('span'); slot.id = 'cat-request-action'; holder.prepend(slot); }
    const html = `<button type="button" class="cat-button" data-request="open">リクエスト ${requests.filter(open).length}件</button>`;
    if (slot.innerHTML !== html) slot.innerHTML = html;
  }
  function copyText(row) {
    const lines = [`# 効果のリクエスト：${row.title}`, '', `- 状態：${row.state}`, `- 出した人：${row.by}（${row.at}）`, '',
      '## 欲しい効果', '', row.want, '', '## 文の例', '', row.example, ''];
    if (row.near) lines.push('## 近い効果タイプ', '', `${row.near}（${typeLabel(row.near)}）`, '');
    if (row.draft) {
      lines.push('## 元の下書き', '', `${row.draft.kind} ${row.draft.id} ${row.draft.name}`, '', '- コスト：（使用時）:FPを3消費', '- 発動時効果：（的中時）:出血4を付与。', '- 特記：', '', '```json', '{"schema": "skill_json_rule_v2", "effects": [ …下書きの特記処理… ]}', '```', '');
    }
    if (row.memo) lines.push('## 管理者のメモ', '', row.memo, '');
    lines.push('## 作り方', '', '新しい効果タイプは `manager/battle/effect_handlers/` にハンドラを足し、`HANDLERS` と `SCHEMAS`（group・label・description・項目）に登録する。`tests/test_effect_schemas.py` のキー一致のテストを通す。開発ルールは `AGENTS.md` に従う。');
    return lines.join('\n');
  }
  function detail(row) {
    if (!row) return '<p class="cat-empty">リクエストを選んでください。</p>';
    const mine = row.by === me;
    const draft = row.draft ? `<button type="button" class="cat-button cat-reference" data-request="goto">${h(row.draft.kind === 'skill' ? 'スキル' : 'バフ')} · ${h(row.draft.id)} ${h(row.draft.name)}</button>` : '<p class="cat-caption">ひもづく下書きはありません。</p>';
    const actions = [
      `<button type="button" class="cat-button" data-request="copy">依頼文としてコピー</button>`,
      mine && row.state === '受付' ? `<button type="button" class="cat-button" data-request="edit">直す</button><button type="button" class="cat-button cat-danger" data-request="withdraw">取り下げる</button>` : '',
    ].join('');
    const admin = as === 'admin' ? `<section class="bo-workspace__card cat-request-admin"><h4>管理者の操作</h4>
      <label class="cat-field">状態<select data-request-field="state">${STATES.map(state => `<option ${state === row.state ? 'selected' : ''}>${state}</option>`).join('')}</select></label>
      <label class="cat-field cat-field-wide">管理者のメモ<textarea rows="3" data-request-field="memo" placeholder="見送りの理由、使う効果タイプなど">${h(row.memo)}</textarea></label>
      <button type="button" class="cat-button cat-primary" data-request="save-admin">状態とメモを保存</button></section>` : '';
    return `<div class="cat-detail-head"><div class="cat-detail-title"><h3>${h(row.title)}</h3><div>${badge(row.state)} <span class="cat-caption">${h(row.by)} · ${h(row.at)}</span></div></div><div class="cat-actions">${actions}</div></div>
      <section class="bo-workspace__card"><h4>欲しい効果</h4><p>${h(row.want)}</p></section>
      <section class="bo-workspace__card"><h4>文の例</h4><p>${h(row.example)}</p></section>
      <section class="bo-workspace__card"><h4>近い効果タイプ</h4><p>${row.near ? `${h(typeLabel(row.near))} <code>${h(row.near)}</code>` : '<span class="cat-caption">指定なし</span>'}</p></section>
      <section class="bo-workspace__card"><h4>元の下書き</h4>${draft}</section>
      ${row.memo ? `<section class="bo-workspace__card cat-request-memo"><h4>管理者のメモ</h4><p>${h(row.memo)}</p></section>` : ''}
      ${admin}
      <details class="cat-json"><summary>コピーされる依頼文（試作で中身を見るため）</summary><pre>${h(copyText(row))}</pre></details>`;
  }
  function formHtml() {
    const types = Object.entries(schemas.effect_types || {});
    const groups = [...new Set(types.map(([, spec]) => spec.group || 'その他'))];
    return `<section class="cat-request-form"><h3>${form.id ? 'リクエストを直す' : '効果のリクエストを出す'}</h3>
      <p class="cat-caption">今の効果タイプでは作れない効果を、管理者に頼みます。出したリクエストは制作者の全員が見られます。</p>
      <label class="cat-field cat-field-wide">題（一言で）<input data-form="title" value="${h(form.title)}" placeholder="例：相手の手番を1つ遅らせる"></label>
      <label class="cat-field cat-field-wide">欲しい効果<textarea rows="3" data-form="want" placeholder="何が起きてほしいか。今の効果でできない所">${h(form.want)}</textarea></label>
      <label class="cat-field cat-field-wide">文の例（ゲームの書き方で）<textarea rows="2" data-form="example" placeholder="例：(的中時):対象の次の行動順を1つ遅らせる。">${h(form.example)}</textarea></label>
      <label class="cat-field">近い効果タイプ（任意）<select data-form="near"><option value="">指定しない</option>${groups.map(group => `<optgroup label="${h(group)}">${types.filter(([, spec]) => (spec.group || 'その他') === group).map(([key, spec]) => `<option value="${h(key)}" ${form.near === key ? 'selected' : ''}>${h(spec.label)}</option>`).join('')}</optgroup>`).join('')}</select></label>
      <div class="cat-field cat-field-wide"><span class="cat-field-label">元の下書き</span>${form.draft ? `<div class="cat-request-draft"><span>${h(form.draft.kind === 'skill' ? 'スキル' : 'バフ')} · ${h(form.draft.id)} ${h(form.draft.name)}</span><button type="button" class="cat-button" data-request="unlink">外す</button></div>` : '<p class="cat-caption">なし（編集の「効果」の節から出すと、その下書きがひもづきます）</p>'}</div>
      <span class="cat-field-error" data-form-error></span>
      <div class="cat-actions"><button type="button" class="cat-button cat-primary" data-request="submit">${form.id ? '直して保存' : 'リクエストを出す'}</button><button type="button" class="cat-button" data-request="cancel">やめる</button></div></section>`;
  }
  function render() {
    const scene = document.querySelector('.cat-scene');
    if (!scene) return;
    const filters = [['open', `受付・対応中 ${requests.filter(open).length}`], ...STATES.slice(2).map(state => [state, `${state} ${requests.filter(row => row.state === state).length}`]), ['all', `すべて ${requests.length}`]];
    const shown = requests.filter(row => filter === 'all' ? true : filter === 'open' ? open(row) : row.state === filter);
    if (!shown.some(row => row.id === selectedId)) selectedId = shown[0]?.id ?? null;
    const list = shown.map(row => `<button type="button" class="bo-workspace__record ${row.id === selectedId ? 'is-selected' : ''}" data-request-id="${row.id}" aria-pressed="${row.id === selectedId}"><div class="cat-record-top"><strong class="bo-workspace__record-title">${h(row.title)}</strong>${badge(row.state)}</div><span class="cat-record-line"><span class="cat-caption">${h(row.by)} · ${h(row.at)}${row.draft ? ` · ${h(row.draft.id)}` : ''}</span></span></button>`).join('') || '<p class="cat-empty">ありません。</p>';
    scene.innerHTML = `<section class="cat-requests"><div class="cat-editbar"><button type="button" class="cat-button" data-request="back">← 戻る</button><h3>効果のリクエスト</h3></div>
      <div class="cat-filters"><nav class="cat-statuses" aria-label="リクエストの状態">${filters.map(([key, label]) => `<button type="button" data-request-filter="${key}" class="${filter === key ? 'is-active' : ''}" aria-pressed="${filter === key}">${h(label)}</button>`).join('')}</nav><button type="button" class="cat-button" data-request="new">＋新しく出す</button></div>
      <div class="bo-workspace__body"><section class="bo-workspace__list-pane" aria-label="リクエスト一覧"><div class="cat-list-heading"><h3>リクエスト</h3><span class="cat-caption">${shown.length}件</span></div><div class="bo-workspace__record-list">${list}</div></section>
      <aside class="bo-workspace__detail-pane">${form ? formHtml() : detail(requests.find(row => row.id === selectedId))}</aside></div></section>`;
  }
  function enter(withForm = null) {
    const scene = document.querySelector('.cat-scene'), back = document.querySelector('#cat-skill-return');
    if (!backup) backup = { html: scene.innerHTML, title: document.querySelector('.bo-workspace__header h2').textContent, back: back?.hidden };
    document.querySelector('.bo-workspace__header h2').textContent = 'マスターデータ';
    if (back) back.hidden = true;
    form = withForm; render();
  }
  function leave() {
    if (!backup) return;
    document.querySelector('.cat-scene').innerHTML = backup.html;
    document.querySelector('.bo-workspace__header h2').textContent = backup.title;
    const back = document.querySelector('#cat-skill-return');
    if (back) back.hidden = backup.back;
    backup = null; form = null;
  }
  function showNotice(text) {
    const box = document.querySelector('.cat-message');
    if (!box) return;
    box.hidden = false; box.textContent = text;
    setTimeout(() => { box.hidden = true; }, 4000);
  }
  function currentDraft() {
    const bar = document.querySelector('.cat-editor-bar, .cat-editbar strong');
    const text = bar?.textContent || '';
    const match = text.match(/([A-Za-z]+-\d+)\s*(.*)/);
    return match ? { kind: document.querySelector('.bo-workspace__header h2')?.textContent === 'スキル' ? 'skill' : 'buff', id: match[1], name: match[2].trim() } : null;
  }

  document.addEventListener('click', async event => {
    const control = event.target.closest('[data-request], [data-request-id], [data-request-filter]');
    if (!control) return;
    event.preventDefault(); event.stopPropagation();
    if (control.dataset.requestId) { selectedId = Number(control.dataset.requestId); form = null; render(); return; }
    if (control.dataset.requestFilter) { filter = control.dataset.requestFilter; form = null; render(); return; }
    const row = requests.find(item => item.id === selectedId);
    const action = control.dataset.request;
    if (action === 'open') return enter();
    if (action === 'from-effects') {
      // 本番では、下書きを保存していなければ「先に下書きを保存してください」と知らせて止める。試作は保存済みとして進む。
      return enter({ title: '', want: '', example: '', near: '', draft: currentDraft(), fromEditor: true });
    }
    if (action === 'back') return leave();
    if (action === 'new') { form = { title: '', want: '', example: '', near: '', draft: null }; render(); return; }
    if (action === 'cancel') { if (form?.fromEditor) { leave(); return; } form = null; render(); return; }
    if (action === 'unlink') { form.draft = null; render(); return; }
    if (action === 'edit') { form = { ...row }; render(); return; }
    if (action === 'withdraw') { if (!await window.showAppConfirm('このリクエストを取り下げますか？')) return; requests.splice(requests.indexOf(row), 1); render(); headerButton(); return; }
    if (action === 'goto') { window.alert(`試作では移りません。本番では ${row.draft.id} の下書きを開きます。`); return; }
    if (action === 'copy') { try { await navigator.clipboard.writeText(copyText(row)); control.textContent = 'コピーしました'; } catch { control.textContent = 'コピーできません（下の中身を使ってください）'; } return; }
    if (action === 'save-admin') {
      row.state = document.querySelector('[data-request-field="state"]').value;
      row.memo = document.querySelector('[data-request-field="memo"]').value.trim();
      render(); headerButton(); return;
    }
    if (action === 'submit') {
      for (const key of ['title', 'want', 'example', 'near']) form[key] = document.querySelector(`[data-form="${key}"]`).value.trim();
      if (!form.title || !form.want) { document.querySelector('[data-form-error]').textContent = '題と欲しい効果は必ず書いてください。'; return; }
      if (form.id) Object.assign(requests.find(item => item.id === form.id), form);
      else { const id = nextId++; requests.unshift({ ...form, id, state: '受付', by: me, at: '2026-11-13', memo: '' }); selectedId = id; }
      const fromEditor = form.fromEditor;
      form = null; filter = 'open'; headerButton();
      if (fromEditor) { leave(); showNotice('リクエストを出しました。上の「リクエスト」から見られます。'); return; }
      render();
    }
  }, true);

  // 効果を持つ種類すべてで、編集の「効果」の節のいちばん上に入口を置く。
  new MutationObserver(() => {
    headerButton();
    const content = document.querySelector('#cat-input-content');
    const active = document.querySelector('.cat-toc [data-section="effects"][aria-current="true"]');
    if (content && active && !content.querySelector('.cat-request-entry')) {
      content.insertAdjacentHTML('afterbegin', '<p class="cat-request-entry">作りたい効果がタイプに無いときは <button type="button" class="cat-link" data-request="from-effects">リクエストを出す</button></p>');
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
