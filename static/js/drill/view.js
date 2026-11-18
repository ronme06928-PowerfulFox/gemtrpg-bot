(function () {
  const h = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const percent = value => `${(Number(value) * 100).toFixed(1)}%`;
  function chart(title, rows, role) {
    if (!rows.length) return `<section class="drill-chart"><h4>${h(title)}</h4><p>この結果は起こりません。</p></section>`;
    const width=Math.max(300,rows.length * 48), height=158;
    const max=Math.max(...rows.map(row=>row.probability),.01);
    return `<section class="drill-chart"><h4>${h(title)}</h4><div class="drill-chart-scroll" tabindex="0" aria-label="${h(title)}の図を横に送る"><svg role="img" aria-label="${h(title)}。各棒の上は確率、下は値" viewBox="0 0 ${width} ${height}" ${rows.length > 10 ? `style="min-width:${rows.length * 30}px" ` : ''}class="drill-bars ${role}">${rows.map((row,index) => {
      const step=width/rows.length, x=step*index, barHeight=row.probability/max*100, y=126-barHeight;
      return `<g><text x="${x+step/2}" y="${y-6}" text-anchor="middle">${percent(row.probability)}</text><rect x="${x+step*.2}" y="${y}" width="${step*.6}" height="${barHeight}"/><text x="${x+step/2}" y="148" text-anchor="middle">${h(row.value)}</text></g>`;
    }).join('')}</svg></div></section>`;
  }
  function result(data, scope) {
    const p=data.probabilities;
    const damage=scope === 'all' ? data.damage_distributions : data.damage_distributions[scope];
    return `<div class="drill-verdict"><strong>${h(data.advantage)}</strong><span>勝率 ${percent(data.win_rate)}</span><small>引き分けは半分の勝ちとして数えます</small></div>
      <div class="drill-probability" aria-label="勝ち・引き分け・負けの割合">${[['win','勝ち'],['draw','引き分け'],['lose','負け']].map(([key,label])=>`<span class="${key}" style="flex-grow:${p[key]}"><span class="drill-visually-hidden">${label} ${percent(p[key])}</span></span>`).join('')}</div>
      <div class="drill-probability-labels">${[['win','勝ち'],['draw','引き分け'],['lose','負け']].map(([key,label])=>`<span>${label} <b>${percent(p[key])}</b></span>`).join('')}</div>
      ${data.has_excluded_effects ? `<details class="drill-caution"><summary>見込みに含まない効果あり（${data.excluded_effects.length}件）</summary><ul>${data.excluded_effects.map(row=>`<li>${row.side === 'actor' ? '使う人' : '相手'}：${h(row.reason)}</li>`).join('')}</ul></details>` : ''}
      <h3>威力の分布</h3><div class="drill-chart-pair">${chart('使う人',data.power_distributions.actor,'actor')}${chart('相手',data.power_distributions.target,'target')}</div>
      <div class="drill-section-title"><h3>受けるダメージの分布</h3><label>結果の範囲 <select data-drill-scope>${[['all','全体'],['on_win','使う人が勝ったとき'],['on_lose','使う人が負けたとき']].map(([key,label])=>`<option value="${key}" ${scope === key ? 'selected' : ''}>${label}</option>`).join('')}</select></label></div>
      <div class="drill-chart-pair">${chart('使う人が受ける',damage.actor,'actor')}${chart('相手が受ける',damage.target,'target')}</div>`;
  }
  window.DrillView = {h,percent,chart,result};
})();
