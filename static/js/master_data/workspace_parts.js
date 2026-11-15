(function () {
  const h = window.CatalogGlossary.escape;
  const historyActions = {import:'取り込み',publish:'保存',deprecate:'廃止',undeprecate:'廃止取り消し',restore:'復元'};

  function history(rows, {revision, restore, button}) {
    if (!rows) return '<p class="cat-caption">履歴を読み込み中…</p>';
    return `<ul class="cat-history">${rows.map(row =>
      `<li><strong>版 ${h(row.revision)} · ${h(historyActions[row.action] || row.action)}</strong>
      <small>${h(row.actor_user_name || row.actor_user_id || 'システム')} / ${h(row.created_at)}</small>
      ${restore && row.revision !== revision ? button('この版に戻す','restore',`data-revision="${h(row.revision)}"`) : ''}
      <details class="cat-json"><summary>JSON</summary><pre>${h(window.CatalogJson.stringify(row.payload))}</pre></details></li>`).join('')}</ul>`;
  }

  function notice(element, dismiss = '') {
    let timer;
    return (message, error = false) => {
      clearTimeout(timer);
      element.textContent = message;
      if (message && dismiss) element.innerHTML = '<span>' + h(message) + '</span>' + dismiss;
      element.hidden = !message;
      element.setAttribute('role', error ? 'alert' : 'status');
      element.classList.toggle('is-error',error);
      if (message && !error) timer = setTimeout(() => { element.hidden = true; }, 3000);
    };
  }

  function confirmDiscard() {
    return window.showAppConfirm('未保存の変更を破棄しますか？',{
      defaultFocus:'cancel', title:'保存していない変更があります', confirmText:'変更を破棄', cancelText:'編集に戻る',
    });
  }

  window.CatalogWorkspaceParts = {h, history, notice, confirmDiscard};
})();
