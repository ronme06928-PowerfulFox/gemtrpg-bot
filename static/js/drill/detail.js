(function () {
  window.mountDrillDetail=function (host,options) {
    const data=window.DrillData, view=window.DrillView, h=view.h;
    const snapshot=JSON.parse(JSON.stringify(options.snapshot)), abort=new AbortController();
    let destroyed=false, skills=[], latest, scope='all';
    const chosen={actor:snapshot.skill_id || '',target:snapshot.target_skill_id || ''};
    host.classList.add('drill');
    host.innerHTML='<header class="drill-header"><h2>詳しく見る</h2><p>ルームの今の値で比べます。スキルはここで選び直せます。</p></header><div class="drill-sides"></div><section class="drill-result" aria-label="勝率の結果"><p>読み込んでいます…</p></section>';
    const result=host.querySelector('.drill-result');
    function message(text) { result.textContent=text; }
    const calculation=window.createDrillCalculation({request:(body,signal)=>data.post('/api/drill/match',body,signal),
      onPending:()=>message('計算しています…'),onError:error=>message(error.message),
      onResult:response=>{latest=response; result.innerHTML=view.result(latest,scope);}});
    function calculate() {
      calculation.cancel(); latest=null;
      if (!chosen.actor) return message('使う人のスキルを選んでください。');
      calculation.schedule({actor:snapshot.actor,target:snapshot.target,skill_id:chosen.actor,target_skill_id:chosen.target || null});
    }
    function render(key) {
      const char=snapshot[key], held=new Set(data.heldSkills(char,skills).map(row=>row.id));
      const rows=[...skills.filter(row=>held.has(row.id)),...skills.filter(row=>!held.has(row.id))];
      return `<fieldset class="drill-side" data-side="${key}"><legend>${key==='actor'?'使う人':'相手'}：${h(char.name)}</legend><p>HP ${h(char.hp)} / MP ${h(char.mp)}</p>
        <label>スキルを探す<input type="search" data-search></label><label>スキル<select data-skill><option value="">${key==='target'?'無し（一方攻撃）':'選んでください'}</option>${rows.map(row=>`<option value="${h(row.id)}" ${chosen[key]===row.id?'selected':''}>${held.has(row.id)?'★ ':''}${h(row.id)} ${h(window.skillNameFromCommands(char,row.id) || row.name)}</option>`).join('')}</select></label></fieldset>`;
    }
    function change(event) {
      if (event.target.matches('[data-drill-scope]')) { scope=event.target.value; if (latest) result.innerHTML=view.result(latest,scope); return; }
      const key=event.target.closest('[data-side]')?.dataset.side;
      if (key && event.target.matches('[data-skill]')) { chosen[key]=event.target.value; calculate(); }
    }
    function input(event) {
      if (!event.target.matches('[data-search]')) return;
      const needle=event.target.value.normalize('NFKC').toLocaleLowerCase();
      for (const option of event.target.closest('[data-side]').querySelectorAll('[data-skill] option'))
        option.hidden=!!option.value && !option.selected && !option.textContent.normalize('NFKC').toLocaleLowerCase().includes(needle);
    }
    host.addEventListener('change',change); host.addEventListener('input',input);
    window.EncyclopediaData.load({room:options.room,signal:abort.signal}).then(catalog=>{
      if (destroyed) return;
      skills=data.readable(catalog.masters,catalog.extra).skill;
      for (const key of ['actor','target']) {
        if (!skills.some(row=>row.id===chosen[key])) chosen[key]=data.heldSkills(snapshot[key],skills)[0]?.id || '';
      }
      host.querySelector('.drill-sides').innerHTML=render('actor')+render('target'); calculate();
    }).catch(error=>{if (!destroyed) message(error.message);});
    return {destroy() { destroyed=true; abort.abort(); calculation.destroy(); host.removeEventListener('change',change); host.removeEventListener('input',input); host.replaceChildren(); host.classList.remove('drill'); }};
  };
})();
