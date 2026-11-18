(function () {
  const h = window.CatalogGlossary.escape;
  window.CatalogBulk = {
    open({ panel, kind, model, labels, rows, admin, apply }) {
      const dialog = document.createElement('dialog');
      dialog.className = 'cat-bulk-dialog';
      dialog.setAttribute('aria-label', '分類と印の一括付け');
      const entries = rows.map(row => ({ entry_id:row.target_id, base_revision:row.revision }));
      const name = row => row.payload.display_name || row.payload.デフォルト名称 || row.payload.name;
      const hidden = row => kind === 'skill' ? row.target_id.startsWith('E-') : row.payload.marks?.includes('enemy');
      labels = Object.fromEntries(Object.entries(labels || {}).filter(([key]) => key !== 'known' || rows.every(hidden)));
      const category = ['buff','glossary'].includes(kind) ? `<label>分類 <select data-bulk-category><option value="__keep">変えない</option>${kind === 'buff' ? '<option value="">未分類</option>' : ''}${model.categories.map(value => `<option>${h(value)}</option>`).join('')}</select></label>` : '';
      dialog.innerHTML = `<h3>分類と印の一括付け</h3><form><div class="cat-bulk-fields">${category}${Object.entries(labels || {}).map(([key,label]) => `<label>${h(label)} <select data-bulk-mark="${h(key)}"><option value="">変えない</option><option value="add">付ける</option><option value="remove">外す</option></select></label>`).join('')}</div><div data-bulk-preview></div><p role="alert"></p><div class="cat-bulk-actions"><button type="button" data-bulk-close>閉じる</button><button type="submit" data-bulk-confirm disabled>${admin ? '確認して公開' : '確認して申請'}</button></div></form>`;
      panel.append(dialog);
      const form = dialog.querySelector('form');
      const confirm = dialog.querySelector('[data-bulk-confirm]');
      let changes, changedRows, running = false;
      function preview() {
        changes = {};
        const selected = dialog.querySelector('[data-bulk-category]')?.value;
        if (selected !== undefined && selected !== '__keep') changes.category = selected;
        for (const action of ['add','remove']) {
          const values = [...dialog.querySelectorAll('[data-bulk-mark]')].filter(control => control.value === action).map(control => control.dataset.bulkMark);
          if (values.length) changes['marks_' + action] = values;
        }
        changedRows = rows.filter(row => ('category' in changes && (row.payload.category || '') !== changes.category)
          || changes.marks_add?.some(mark => !row.payload.marks?.includes(mark))
          || changes.marks_remove?.some(mark => row.payload.marks?.includes(mark)));
        dialog.querySelector('[data-bulk-preview]').innerHTML = `<h4>変更する物 ${changedRows.length}件</h4><ul>${changedRows.map(row => `<li>${h(row.target_id)} ${h(name(row))}</li>`).join('')}</ul><p>既存の下書き・検査エラー・版の変わった物は飛ばします。${admin ? '下書き・申請・承認' : '下書き・申請'}を1件ずつ行います。</p>`;
        confirm.disabled = !changedRows.length;
      }
      form.addEventListener('change', preview);
      form.addEventListener('submit', async event => {
        event.preventDefault();
        if (running || !changedRows.length) return;
        running = true;
        form.querySelectorAll('button,select').forEach(control => { control.disabled = true; });
        try {
          const ids = new Set(changedRows.map(row => row.target_id));
          const result = await apply({ entries:entries.filter(row => ids.has(row.entry_id)), changes });
          dialog.querySelector('[data-bulk-preview]').innerHTML = `<h4>${admin ? '公開' : '申請'} ${result.changed}件・飛ばした物 ${result.skipped}件</h4><ul>${result.results.map(row => `<li>${h(row.entry_id)}：${h(row.reason || (row.status === 'published' ? '公開しました' : '申請しました'))}</li>`).join('')}</ul>`;
          dialog.querySelector('.cat-bulk-fields').hidden = true;
          confirm.hidden = true;
        } catch (error) {
          dialog.querySelector('[role="alert"]').textContent = error.message;
          form.querySelectorAll('select').forEach(control => { control.disabled = false; });
          confirm.disabled = false;
        } finally {
          running = false;
          dialog.querySelector('[data-bulk-close]').disabled = false;
        }
      });
      dialog.querySelector('[data-bulk-close]').addEventListener('click', () => dialog.close());
      dialog.addEventListener('cancel', event => { if (running) event.preventDefault(); });
      dialog.addEventListener('close', () => dialog.remove(), { once:true });
      preview();
      dialog.showModal();
    },
  };
})();
