(function () {
  const data=window.DrillData, view=window.DrillView, h=view.h;
  const clone=value=>JSON.parse(JSON.stringify(value));
  const params=['体力','精神','筋力','敏捷','技量','知力','物理補正','魔法補正','ダイス威力','出身'];
  const states=['出血','破裂','亀裂','戦慄','荊棘'];
  const number=(label,value,attributes)=>`<label>${h(label)}<input type="number" step="1" value="${h(value ?? 0)}" ${attributes}></label>`;
  function mountDrill(host, options={}) {
    host.classList.add('drill');
    host.innerHTML='<header class="drill-header"><h2>演習場</h2><p>キャラクターとスキルを選び、勝率を比べます。ここで変えた値はキャラクターには残りません。</p></header><div class="drill-sides"></div><section class="drill-result" aria-label="勝率の結果"><p role="status">読み込んでいます…</p></section>';
    const result=host.querySelector('.drill-result');
    const rootAbort=new AbortController();
    let destroyed=false, owned=[], readable, latest, scope='all';
    const sides=Object.fromEntries(['actor','target'].map(key=>[key,{source:'blank',id:'',character:data.blank(key === 'actor' ? '使う人' : '相手'),skill:'',query:'',revision:0,invalid:new Set()}]));
    const controllers={};
    function message(text,error=false) {
      result.innerHTML=`<p role="${error ? 'alert' : 'status'}"></p>`;
      result.querySelector('p').textContent=text;
      result.setAttribute('aria-busy','false');
      host.dataset.drillState=error ? 'error' : 'waiting';
    }
    const calculation=window.createDrillCalculation({
      request:(body,signal)=>data.post('/api/drill/match',body,signal),
      onPending:()=>{ message('計算しています…'); result.setAttribute('aria-busy','true'); },
      onError:error=>message(error.message,true),
      onResult:response=>{ latest=response; renderResult(); },
    });
    function renderResult() {
      result.innerHTML=view.result(latest,scope);
      result.setAttribute('aria-busy','false');
      host.dataset.drillState='ready';
    }
    function calculate() {
      latest=null;
      calculation.cancel();
      if (Object.values(sides).some(side=>side.loading)) return message('キャラクターを読み込んでいます…');
      if (Object.values(sides).some(side=>side.error)) return message('キャラクターを選び直してください。',true);
      if (Object.values(sides).some(side=>side.invalid.size)) return message('入力中の数値を確認してください。',true);
      if (!sides.actor.skill) return message('使う人のスキルを選んでください。');
      calculation.schedule({actor:clone(sides.actor.character),target:clone(sides.target.character),
        skill_id:sides.actor.skill,target_skill_id:sides.target.skill || null});
    }
    function rowsValue(char,field,key) {
      return char[field]?.find(row=>row[field === 'params' ? 'label' : 'name'] === key)?.value ?? 0;
    }
    function numericRows(char,field,names) {
      return names.map(key=>number(key === '出身' ? '出身（国の番号）' : key,rowsValue(char,field,key),`data-number="${field}" data-key="${h(key)}"`)).join('');
    }
    function skillOptions(key) {
      const side=sides[key], held=data.heldSkills(side.character,readable.skill);
      const needle=side.query.normalize('NFKC').toLocaleLowerCase();
      const matches=row=>row.id === side.skill || !needle || `${row.id} ${row.name}`.normalize('NFKC').toLocaleLowerCase().includes(needle);
      const ids=new Set(held.map(row=>row.id));
      const group=(label,rows)=>`<optgroup label="${label}">${rows.filter(matches).map(row=>`<option value="${h(row.id)}" ${side.skill === row.id ? 'selected' : ''}>${h(row.id)} ${h(row.name)}</option>`).join('')}</optgroup>`;
      return `<option value="">${key === 'target' ? '無し（一方攻撃）' : 'スキルを選ぶ'}</option>${group('所持スキル',held)}${group('ほかのスキル',readable.skill.filter(row=>!ids.has(row.id)))}`;
    }
    function renderSide(key) {
      const side=sides[key], char=side.character;
      // A rebuilt form restores the last valid values, including removed buff inputs.
      side.invalid.clear();
      const records=side.source === 'owned' ? owned : readable.enemy;
      const names=[...new Set([...params,...(char.params || []).map(row=>row.label)])];
      const stateNames=[...new Set([...states,...(char.states || []).map(row=>row.name)])].filter(name=>name !== 'FP');
      const markup=`<fieldset class="drill-side" data-side="${key}"><legend>${key === 'actor' ? '使う人' : '相手'}</legend>
        <div class="drill-source"><label>キャラクターの選び方<select data-source>${[['blank','素の値'],['owned','持ちキャラ'],['unit','敵ユニット']].map(([value,label])=>`<option value="${value}" ${side.source === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
        <label ${side.source === 'blank' ? 'hidden' : ''}>${side.source === 'owned' ? '持ちキャラ' : '敵ユニット'}<select data-record ${side.loading ? 'disabled' : ''}><option value="">選んでください</option>${records.map(row=>`<option value="${h(row.id)}" ${side.id === row.id ? 'selected' : ''}>${h(row.name)}</option>`).join('')}</select></label></div>
        <p class="drill-side-message" role="status">${side.loading ? '読み込んでいます…' : ''}</p>
        <label>名前<input type="text" maxlength="2048" data-name value="${h(char.name)}"></label>
        <div class="drill-core">${number('HP',char.hp,'data-number="root" data-key="hp"')}${number('MP',char.mp,'data-number="root" data-key="mp"')}${number('FP',rowsValue(char,'states','FP'),'data-number="states" data-key="FP"')}</div>
        <details class="drill-editor" open><summary>能力値・補正・出身</summary><div class="drill-values">${numericRows(char,'params',names)}</div><div class="drill-add-row"><input data-new-param placeholder="追加する能力の名前" aria-label="追加する能力の名前"><button type="button" data-add-row="params">追加</button></div></details>
        <details class="drill-editor"><summary>状態・最大HP/MP</summary><div class="drill-values">${number('最大HP',char.maxHp,'data-number="root" data-key="maxHp"')}${number('最大MP',char.maxMp,'data-number="root" data-key="maxMp"')}${numericRows(char,'states',stateNames)}</div><div class="drill-add-row"><input data-new-state placeholder="追加する状態の名前" aria-label="追加する状態の名前"><button type="button" data-add-row="states">追加</button></div></details>
        <details class="drill-editor"><summary>バフ（${char.special_buffs?.length || 0}件）</summary><div class="drill-buffs">${(char.special_buffs || []).map((buff,index)=>`<div class="drill-buff"><div><strong>${h(readable.buff.find(row=>row.id === buff.buff_id)?.name || buff.name || buff.buff_id)}</strong><button type="button" data-remove-buff="${index}">外す</button></div><div class="drill-core">${number('値',buff.data?.value ?? buff.value ?? 1,`data-buff="${index}" data-buff-field="value"`)}${number('回数',buff.count ?? 1,`data-buff="${index}" data-buff-field="count"`)}${number('持続',buff.lasting ?? 1,`data-buff="${index}" data-buff-field="lasting"`)}</div></div>`).join('')}</div><div class="drill-add-row"><select data-buff-choice aria-label="追加するバフ">${readable.buff.map(row=>`<option value="${h(row.id)}">${h(row.id)} ${h(row.name)}</option>`).join('')}</select><button type="button" data-add-buff>付ける</button></div></details>
        <div class="drill-skill"><label>スキルを探す<input type="search" data-skill-search placeholder="ID・名前で検索" value="${h(side.query)}"></label><label>${key === 'actor' ? '使う' : '相手の'}スキル<select data-skill>${skillOptions(key)}</select></label></div></fieldset>`;
      const old=host.querySelector(`[data-side="${key}"]`);
      if (old) old.outerHTML=markup; else host.querySelector('.drill-sides').insertAdjacentHTML('beforeend',markup);
    }
    async function selectRecord(key,id) {
      const side=sides[key], revision=++side.revision;
      controllers[key]?.abort();
      side.id=id; side.error=false; side.invalid.clear(); side.skill=''; side.character=data.blank(key === 'actor' ? '使う人' : '相手');
      side.loading=!!id;
      renderSide(key); calculate();
      if (!id) return;
      const abort=new AbortController(); controllers[key]=abort;
      try {
        const response=await data.post('/api/drill/character',{source:side.source,id,side:key === 'actor' ? 'ally' : 'enemy'},abort.signal);
        if (destroyed || side.revision !== revision) return;
        side.character=response.character;
        side.skill=data.heldSkills(side.character,readable.skill)[0]?.id || '';
        side.loading=false; renderSide(key); calculate();
      } catch(error) {
        if (destroyed || side.revision !== revision || error.name === 'AbortError') return;
        side.loading=false; side.error=true; renderSide(key); calculate();
        const notice=host.querySelector(`[data-side="${key}"] .drill-side-message`);
        notice.textContent=error.message; notice.setAttribute('role','alert');
      }
    }
    function input(event) {
      const control=event.target, key=control.closest('[data-side]')?.dataset.side;
      if (!key) return;
      const side=sides[key], char=side.character;
      if (control.hasAttribute('data-skill-search')) {
        side.query=control.value;
        host.querySelector(`[data-side="${key}"] [data-skill]`).innerHTML=skillOptions(key);
        return;
      }
      if (control.hasAttribute('data-name')) { char.name=control.value; calculate(); return; }
      if (!control.dataset.number && !control.hasAttribute('data-buff')) return;
      const invalidKey=control.dataset.number+':'+control.dataset.key+':'+control.dataset.buff+':'+control.dataset.buffField;
      if (!Number.isFinite(control.valueAsNumber)) { side.invalid.add(invalidKey); calculate(); return; }
      side.invalid.delete(invalidKey);
      const value=control.valueAsNumber;
      if (control.hasAttribute('data-buff')) {
        const buff=char.special_buffs[Number(control.dataset.buff)];
        if (control.dataset.buffField === 'value') { buff.data={...buff.data,value}; if ('value' in buff) buff.value=value; }
        else buff[control.dataset.buffField]=value;
      } else if (control.dataset.number === 'root') {
        char[control.dataset.key]=value;
        const label={hp:'HP',mp:'MP'}[control.dataset.key];
        const status=char.status?.find(row=>row.label === label);
        if (status) status.value=value;
      } else {
        const field=control.dataset.number, name=field === 'params' ? 'label' : 'name';
        const row=char[field].find(row=>row[name] === control.dataset.key);
        if (row) row.value=value; else char[field].push({[name]:control.dataset.key,value});
      }
      calculate();
    }
    function change(event) {
      const control=event.target;
      if (control.hasAttribute('data-drill-scope')) { scope=control.value; if (latest) renderResult(); return; }
      const key=control.closest('[data-side]')?.dataset.side;
      if (!key) return;
      const side=sides[key];
      if (control.hasAttribute('data-source')) { side.source=control.value; selectRecord(key,''); }
      else if (control.hasAttribute('data-record')) selectRecord(key,control.value);
      else if (control.hasAttribute('data-skill')) { side.skill=control.value; calculate(); }
    }
    function click(event) {
      const control=event.target.closest('button'), key=control?.closest('[data-side]')?.dataset.side;
      if (!key) return;
      const side=sides[key], char=side.character, panel=control.closest('[data-side]');
      if (control.dataset.addRow) {
        const field=control.dataset.addRow, node=panel.querySelector(field === 'params' ? '[data-new-param]' : '[data-new-state]');
        const name=node.value.trim(), label=field === 'params' ? 'label' : 'name';
        if (!name || char[field].some(row=>row[label] === name)) return;
        char[field].push({[label]:name,value:0}); renderSide(key);
        host.querySelector(`[data-side="${key}"] ${field === 'params' ? '[data-new-param]' : '[data-new-state]'}`).closest('details').open=true;
      } else if (control.hasAttribute('data-add-buff')) {
        const row=readable.buff.find(row=>row.id === panel.querySelector('[data-buff-choice]').value);
        if (!row) return;
        char.special_buffs.push({buff_id:row.id,name:row.data.name || row.name,lasting:row.data.default_duration ?? 1,delay:0,count:1,data:{value:1}});
        renderSide(key);
      } else if (control.hasAttribute('data-remove-buff')) {
        char.special_buffs.splice(Number(control.dataset.removeBuff),1); renderSide(key);
      } else return;
      if (control.hasAttribute('data-add-buff') || control.hasAttribute('data-remove-buff'))
        host.querySelector(`[data-side="${key}"] .drill-buffs`).closest('details').open=true;
      calculate();
    }
    host.addEventListener('input',input); host.addEventListener('change',change); host.addEventListener('click',click);
    async function load() {
      try {
        const [catalog,characters]=await Promise.all([window.EncyclopediaData.load({signal:rootAbort.signal}),data.json('/api/owned_characters',{signal:rootAbort.signal})]);
        if (destroyed) return;
        readable=data.readable(catalog.masters,catalog.extra);
        owned=characters.characters;
        for (const key of ['actor','target']) {
          const saved=options.initialState?.[key];
          if (saved && (saved.source === 'blank' || (saved.source === 'owned' ? owned : readable.enemy).some(row=>row.id === saved.id))) {
            Object.assign(sides[key],clone(saved),{invalid:new Set(),revision:0,loading:false});
            if (!readable.skill.some(row=>row.id === sides[key].skill)) sides[key].skill='';
          }
          renderSide(key);
        }
        calculate();
      } catch(error) { if (!destroyed) message(error.message,true); }
    }
    load();
    return {
      getState() { return Object.fromEntries(Object.entries(sides).map(([key,side])=>[key,clone({source:side.source,id:side.id,character:side.character,skill:side.skill,query:side.query})])); },
      destroy() {
        destroyed=true; rootAbort.abort(); calculation.destroy(); Object.values(controllers).forEach(controller=>controller.abort());
        host.removeEventListener('input',input); host.removeEventListener('change',change); host.removeEventListener('click',click);
        host.replaceChildren(); host.classList.remove('drill');
      },
    };
  }
  window.mountDrill=mountDrill;
})();
