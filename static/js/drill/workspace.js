(function () {
  const data=window.DrillData, h=window.DrillView.h;
  function mountDrill(host, options={}) {
    if (options.snapshot) return window.mountDrillDetail(host,options);
    host.classList.add('drill');
    host.innerHTML='<header class="drill-header"><h2>演習場</h2><p>2人を選んで、保存しないルームで練習します。値はルームの📝で変更できます。</p></header><div class="drill-sides"></div><p data-drill-message role="status">読み込んでいます…</p><button type="button" class="drill-start" disabled>この2人で練習する</button>';
    const abort=new AbortController(), sides={}, revisions={actor:0,target:0};
    const button=host.querySelector('.drill-start'), message=host.querySelector('[data-drill-message]');
    let destroyed=false, owned=[], units=[], skills=[];
    const saved=options.initialState || window.PracticeRoom?.getSelection() || {};
    for (const key of ['actor','target']) sides[key]={source:'blank',name:key==='actor'?'使う人':'相手',...saved[key],skills:[...(saved[key]?.skills || [])]};
    function ready() { button.disabled=Object.values(sides).some(side=>side.loading || side.error || (side.source!=='blank' && !side.id)); }
    function availableSkills(key) {
      const side=sides[key], character=side.character || (side.source==='blank'
        ? {commands:skills.find(row=>row.id==='Ps-00')?.data.チャットパレット || ''} : {});
      const held=new Set(data.heldSkills(character,skills).map(row=>row.id));
      return skills.filter(row=>!side.skills.includes(row.id) && !held.has(row.id));
    }
    function skillOptions(key,needle='') {
      const query=needle.normalize('NFKC').toLocaleLowerCase();
      return '<option value="">選んでください</option>'+availableSkills(key)
        .filter(row=>(row.id+' '+row.name).normalize('NFKC').toLocaleLowerCase().includes(query))
        .map(row=>`<option value="${h(row.id)}">${h(row.id)} ${h(row.name)}</option>`).join('');
    }
    function render(key) {
      const side=sides[key], records=side.source==='owned'?owned:units;
      const html=`<fieldset class="drill-side" data-side="${key}"><legend>${key==='actor'?'使う人':'相手'}</legend>
        <label>キャラクターの選び方<select data-source>${[['blank','素の値'],['owned','持ちキャラ'],['unit','敵ユニット']].map(([id,name])=>`<option value="${id}" ${side.source===id?'selected':''}>${name}</option>`).join('')}</select></label>
        ${side.source==='blank'?`<label>名前<input data-name maxlength="100" value="${h(side.name)}"></label><p>HP20・MP20、基本の一太刀から始めます。</p>`:
          `<label>${side.source==='owned'?'持ちキャラ':'敵ユニット'}<select data-record><option value="">選んでください</option>${records.map(row=>`<option value="${h(row.id)}" ${side.id===row.id?'selected':''}>${h(row.name)}</option>`).join('')}</select></label>`}
        <p class="drill-selection-preview" role="status">${h(side.loading?'読み込んでいます…':side.error || (side.character?`${side.character.name} · HP ${side.character.hp} / MP ${side.character.mp}`:''))}</p>
        <section class="drill-add-skills" aria-label="スキルを足す"><h3>スキルを足す</h3>
          <label>ID・名前で絞る<input type="search" data-add-search></label>
          <div class="drill-add-row"><label>スキル<select data-add-picker>${skillOptions(key)}</select></label><button type="button" data-add-skill>足す</button></div>
          <ul class="drill-skill-tags" aria-label="足したスキル">${side.skills.map(id=>`<li>${h(id)} ${h(skills.find(row=>row.id===id)?.name || '')}<button type="button" data-remove-skill="${h(id)}" aria-label="${h(id)}を外す">×</button></li>`).join('')}</ul>
        </section></fieldset>`;
      const old=host.querySelector(`[data-side="${key}"]`);
      if (old) old.outerHTML=html; else host.querySelector('.drill-sides').insertAdjacentHTML('beforeend',html);
      ready();
    }
    async function select(key) {
      const side=sides[key], revision=++revisions[key];
      delete side.character; side.error=''; side.loading=side.source!=='blank' && !!side.id; render(key);
      if (!side.loading) return;
      try {
        const response=await data.post('/api/drill/character',{source:side.source,id:side.id,side:key==='actor'?'ally':'enemy'},abort.signal);
        if (destroyed || revision!==revisions[key]) return;
        side.character=response.character;
      } catch(error) { if (!destroyed && revision===revisions[key]) side.error=error.message; }
      if (!destroyed && revision===revisions[key]) { side.loading=false; render(key); }
    }
    function change(event) {
      const key=event.target.closest('[data-side]')?.dataset.side;
      if (!key) return;
      if (event.target.matches('[data-source]')) { sides[key].source=event.target.value; sides[key].id=''; select(key); }
      if (event.target.matches('[data-record]')) { sides[key].id=event.target.value; select(key); }
    }
    function input(event) {
      if (event.target.matches('[data-name]')) sides[event.target.closest('[data-side]').dataset.side].name=event.target.value;
      if (event.target.matches('[data-add-search]')) {
        const field=event.target.closest('[data-side]');
        field.querySelector('[data-add-picker]').innerHTML=skillOptions(field.dataset.side,event.target.value);
      }
    }
    function click(event) {
      const key=event.target.closest('[data-side]')?.dataset.side;
      if (!key) return;
      if (event.target.matches('[data-add-skill]')) {
        const id=host.querySelector(`[data-side="${key}"] [data-add-picker]`).value;
        if (availableSkills(key).some(row=>row.id===id)) { sides[key].skills.push(id); render(key); }
      }
      if (event.target.matches('[data-remove-skill]')) {
        sides[key].skills=sides[key].skills.filter(id=>id!==event.target.dataset.removeSkill); render(key);
      }
    }
    async function start() {
      button.disabled=true; message.textContent='ルームを作っています…';
      try {
        const selection=Object.fromEntries(Object.entries(sides).map(([key,side])=>[key,{...(side.source==='blank'?{source:'blank',name:side.name}:{source:side.source,id:side.id}),skills:[...side.skills]}]));
        const response=await data.post('/api/drill/practice',selection,abort.signal);
        if (!destroyed) await joinRoom(response.room_name,response.state,{role:'GM',gmPin:''});
      } catch(error) { if (!destroyed) { message.textContent=error.message; message.setAttribute('role','alert'); ready(); } }
    }
    host.addEventListener('change',change); host.addEventListener('input',input); host.addEventListener('click',click); button.addEventListener('click',start);
    Promise.all([window.EncyclopediaData.load({signal:abort.signal}),data.json('/api/owned_characters',{signal:abort.signal})]).then(([catalog,characters])=>{
      if (destroyed) return;
      const readable=data.readable(catalog.masters,catalog.extra);
      owned=characters.characters; units=readable.enemy; skills=readable.skill;
      message.textContent='';
      for (const key of ['actor','target']) {
        const records=sides[key].source==='owned'?owned:units;
        if (sides[key].source!=='blank' && !records.some(row=>row.id===sides[key].id)) sides[key].id='';
        select(key);
      }
    }).catch(error=>{ if (!destroyed) { message.textContent=error.message; message.setAttribute('role','alert'); } });
    return {getState:()=>Object.fromEntries(Object.entries(sides).map(([key,side])=>[key,{source:side.source,id:side.id,name:side.name,skills:[...side.skills]}])),
      destroy() { destroyed=true; abort.abort(); host.removeEventListener('change',change); host.removeEventListener('input',input); host.removeEventListener('click',click); button.removeEventListener('click',start); host.replaceChildren(); host.classList.remove('drill'); }};
  }
  window.mountDrill=mountDrill;
})();
