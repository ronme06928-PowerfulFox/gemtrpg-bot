const $ = (selector, root = document) => root.querySelector(selector);
const h = value => String(value ?? '').replace(/[&<>"']/g, char =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[char]);
const unit = id => catalog.units.find(row => row.id === id);
const stage = id => catalog.stages.find(row => row.id === id);
const formation = (id, side = 'enemy') => catalog[side].find(row => row.id === id);
const boardWidth = 15;
const boardHeight = 9;
const imageRoot = '../../static/images/characters/';
const art = {ally:['女冒険者.png','男冒険者.png'],enemy:['人狼型シュラーカー.png','小人型シュラーカー.png']};
const positions = [{x:3,y:2},{x:4,y:4},{x:2,y:5},{x:5,y:6}];
const pcs = catalog.units.filter(row => row.ally).slice(0,4).map((row,i) => ({
  ...positions[i], ...row, name:['セラ','ノア',row.name,row.name][i], side:'ally', current:Math.round(row.hp * [0.58,0.74,0.46,0.68][i]), art:art.ally[i%2],
}));
const makeEnemy = (row,i,point) => ({
  ...row, ...point, side:'enemy', current:row.hp, art:art.enemy[i%2],
});
const previous = Array.from({length:2}, (_,i) => makeEnemy(unit(catalog.enemy[0].members[0].id),i,{x:10+i*2,y:4+i}));
const emptyDraft = () => ({
  name:'', memo:'', stageId:'', enemyId:'', allyId:'', owner:'', extras:[], checked:{background:true,effects:true,avatar:true}, mode:'replace',
});
const stageSample = catalog.stages[0];
const firstGroup = catalog.enemy[0];
const demo = [
  {...emptyDraft(), id:'demo-stage', name:stageSample.name, stageId:stageSample.id,
    extras:[{id:firstGroup.members[0].id,count:4}]},
  {...emptyDraft(), id:'demo-formation', name:firstGroup.name, enemyId:firstGroup.id, mode:'add'},
];
const room = {
  scene:'A', viewer:'GM', theme:'night', type:'stage', search:'', draft:emptyDraft(), queue:[],
  done:new Set(), placed:{B:null,C:null},
  terrain:{B:{name:'遺跡への街道', usesStageBackground:false, effects:[]},C:{
    name:stageSample.name, usesStageBackground:true, effects:stageSample.effects.map(row=>row.display_name),
  }},
  unplaced:[], active:null, pan:{x:0,y:0}, tight:false, entered:false, applied:null, detail:false,
};
const screen = $('#screen');
const dialog = $('#dialog');
let dialogAction;
let pointer;
try { room.queue = JSON.parse(localStorage.getItem('room-queue-proto-v1') || '[]'); } catch {}
function persistQueue() {
  try { localStorage.setItem('room-queue-proto-v1',JSON.stringify(room.queue)); } catch {}
}

function encounter(entry) {
  const selected = stage(entry.stageId);
  const group = formation(entry.enemyId || selected?.enemy);
  const ally = formation(entry.allyId,'ally');
  const lookup = (rows = []) => rows.flatMap(({id,count}) => Array.from({length:count}, () => unit(id)));
  return {
    stage:selected, group, enemies:lookup([...(group?.members || []), ...entry.extras]), allies:lookup(ally?.members),
    min:selected?.minimum || 1,
    effects:entry.checked.effects ? selected?.effects || [] : [],
    background:!!(entry.checked.background && selected),
    avatar:entry.checked.avatar && selected?.avatar,
  };
}

function rowsForSession() {
  if (room.queue.length >= 2) return room.queue;
  if (room.queue.length === 1) return [...room.queue,demo[1]];
  return demo;
}

function button(label, action, extra = '') {
  return '<button type="button" data-action="' + action + '" ' + extra + '>' + label + '</button>';
}
const selected = condition => ' aria-pressed="' + condition + '"';
const check = value => value ? ' checked' : '';
const badge = (label, tone = '') => '<span class="pill ' + tone + '">' + label + '</span>';

function panel(title, content, action = '', extra = '') {
  return '<section class="panel ' + extra + '"><header class="panel-heading"><h3>' + title + '</h3>' +
    action + '</header><div class="panel-body">' + content + '</div></section>';
}

function queueEntry(entry,index,action = '') {
  const info = encounter(entry);
  return '<article class="queue-row"><div class="queue-title"><span class="queue-index">' +
    String(index+1).padStart(2,'0') + '</span><strong>' + h(entry.name) + '</strong>' +
    (room.done.has(entry.id) ? badge('済','ok') : '') + '</div><small>' +
    (info.stage ? 'ステージ' : '敵編成') + ' · 敵 ' + info.enemies.length + ' 体' +
    (info.allies.length ? ' · 味方 ' + info.allies.length + ' 体' : '') + '</small>' +
    (entry.memo ? '<p class="muted">' + h(entry.memo) + '</p>' : '') +
    (action ? '<div class="actions">' + action + '</div>' : '') + '</article>';
}

function assetRows() {
  const sources = {
    stage:catalog.stages, enemy:catalog.enemy, unit:catalog.units.filter(row=>row.enemy), ally:catalog.ally,
  };
  const matching = sources[room.type].filter(row => row.name.includes(room.search.trim()));
  return matching.map(row => {
    const description = room.type === 'stage' ? row.concept :
      row.members ? row.members.map(member => unit(member.id).name + ' × ' + member.count).join('、') : '敵ユニット';
    return '<article class="asset"><div><strong>' + h(row.name) + '</strong><p>' + h(description) +
      '</p></div>' + button(room.type === 'unit' ? '追加' : '選択','add-asset','data-id="'+h(row.id)+'"') + '</article>';
  }).join('') || '<p class="empty">該当なし</p>';
}

function prep() {
  const draft = room.draft;
  const info = encounter(draft);
  const details = '<div class="fields"><label>遭遇名<input data-field="name" value="' + h(draft.name) +
    '"></label><label>メモ<textarea data-field="memo" rows="2">' + h(draft.memo) + '</textarea></label></div>';
  const sources = [
    ['ステージ',info.stage?.name,'stageId'],['敵編成',info.group?.name,draft.enemyId ? 'enemyId' : ''],
    ['味方編成',formation(draft.allyId,'ally')?.name,'allyId'],
  ].filter(([,name])=>name).map(([label,name,field])=>'<div class="asset"><span><small>'+label+'</small><br><strong>'+h(name)+
    '</strong></span>'+(field ? button('解除','clear-asset','data-field="'+field+'"') : '')+'</div>').join('');
  const extras = draft.extras.map((row,index)=>'<div class="asset"><span><small>追加ユニット</small><br><strong>'+
    h(unit(row.id).name)+'</strong></span><div class="actions"><input type="number" min="1" max="150" aria-label="'+h(unit(row.id).name)+
    'の数" value="'+row.count+'" data-count="'+index+'">' + button('外す','remove-extra','data-index="'+index+'"')+'</div></div>').join('');
  const options = '<div class="options"><label>既存の敵 <select data-field="mode"><option value="replace"'+
    (draft.mode==='replace'?' selected':'')+'>置換</option><option value="add"'+(draft.mode==='add'?' selected':'')+
    '>追加</option></select></label>' + (info.allies.length ? '<label>味方の担当 <select data-field="owner"><option value="">未設定</option>'+
      ['GM','PL 1','PL 2','PL 3','PL 4'].map(name=>'<option'+(draft.owner===name?' selected':'')+'>'+name+'</option>').join('')+
      '</select></label>' : '') + (info.stage ? [
      ['background','背景を適用'],['effects','フィールド効果を差し替え'],['avatar','ステージアバターを適用'],
    ].map(([key,label])=>'<label><input type="checkbox" data-option="'+key+'"'+check(draft.checked[key])+'>'+label+'</label>').join('') : '') + '</div>';
  const totals = '<p class="room-note">' + badge('敵 <b id="enemy-count">'+info.enemies.length+'</b> 体') +
    badge('味方 '+info.allies.length+' 体')+'</p>';
  const typeTabs = [['stage','ステージ'],['enemy','敵編成'],['unit','ユニット'],['ally','味方編成']].map(([key,label])=>
    button(label,'asset-tab','data-id="'+key+'"'+selected(room.type===key))).join('');
  return '<div class="prep" data-theme="'+room.theme+'"><div class="page-heading"><h2>遭遇準備</h2>'+
    badge('GM')+'</div><div class="prep-grid">' +
    panel('待機列', room.queue.map((entry,index)=>queueEntry(entry,index,button('編集','edit-entry','data-id="'+
      h(entry.id)+'"')+button('外す','remove-entry','data-id="'+h(entry.id)+'"'))).join('') ||
      '<p class="empty">遭遇なし</p>',button('＋ 新規','new-entry')) +
    panel(draft.id ? '遭遇を編集' : '新規遭遇','<div class="stack">'+ details+sources+extras+options+totals+
      '<div class="actions">'+button('保存','validate','class="primary"')+'</div></div>') +
    panel('資源を選択','<div class="stack"><div class="actions">'+typeTabs+'</div><input data-asset-search type="search" aria-label="資源検索" placeholder="名称で検索" value="'+
      h(room.search)+'"><div id="assets">'+assetRows()+'</div></div>') + '</div></div>';
}

function players() {
  return '<div class="party" aria-label="PCのHP">' + pcs.map(row => '<span>'+h(row.name)+' <b>HP '+row.current+'/'+row.hp+'</b></span>').join('')+'</div>';
}
function currentActors() {
  return room.placed[room.scene] || (room.scene==='B' ? [...pcs,...previous] : room.placed.B || [...pcs,
    ...encounter(demo[0]).enemies.map((row,i)=>makeEnemy(row,i,{x:9+i%3,y:3+Math.floor(i/3)}))]);
}
function occupied() {
  return new Set(currentActors().map(row=>key(row.x,row.y)));
}
const key = (x,y) => x + ':' + y;
const inBounds = ({x,y}) => x>=0 && x<boardWidth && y>=0 && y<boardHeight;
function blocked(x,y) {
  if (room.tight && room.scene==='B') return !['10:2','11:2','10:3'].includes(key(x,y)) && !occupied().has(key(x,y));
  return (x===0 || x===boardWidth-1) && (y<2 || y>6);
}
function positionStyle(x,y) {
  return 'left:'+(x * 100 / boardWidth)+'%;top:'+(y * 100 / boardHeight)+'%';
}
function mapPieces() {
  return currentActors().map(row=>'<div class="piece '+row.side+'" style="'+positionStyle(row.x,row.y)+
    '"><div class="piece-body"><img src="'+imageRoot+h(row.art)+'" alt=""></div><span class="piece-name">'+
    h(row.name)+'</span></div>').join('');
}
function board() {
  const terrain = room.terrain[room.scene];
  const encounters = rowsForSession();
  const waiting = encounters.map((entry,i)=>queueEntry(entry,i,
    button('登場','appear','data-id="'+h(entry.id)+'"'+(room.active?' disabled':'')))).join('');
  const extras = room.viewer==='GM' && !room.active ? '<aside class="room-side">'+panel('待機列',waiting,'<small>'+encounters.length+' 件</small>')+'</aside>' : '';
  const place = room.viewer==='GM' && room.active;
  const boardLabel = room.scene==='B' && !room.entered && !place && !room.placed.B ? '探索マップ' : '戦闘盤面';
  return '<div class="page-heading"><div class="board-heading"><h2>'+boardLabel+'</h2>'+
    players()+'</div>' + (room.viewer==='GM' && room.scene==='C' && !place ? button('＋ 予定外の増援','reinforcement','class="primary"') : '') +
    '</div><div class="room-grid">'+ extras + '<section class="panel"><header class="panel-heading"><div class="room-note"><strong>'+
    h(terrain.name)+'</strong>'+badge(terrain.usesStageBackground ? '背景：氷の遺跡' : '背景：街道')+
    badge('効果：'+h(terrain.effects.join('、') || 'なし'))+'</div>'+
    (room.viewer==='GM' && room.placed[room.scene] ? badge('配置済','ok') : '')+
    '</header><div class="board-frame"><div class="board-viewport" tabindex="0" aria-label="'+
    (place ? '配置マスを選択' : '戦闘盤面')+'"><div class="board-map '+(terrain.usesStageBackground?'':'road')+
    '"><div class="tiles">'+Array.from({length:boardWidth*boardHeight},(_,i)=>'<span class="tile'+
      (blocked(i%boardWidth,Math.floor(i/boardWidth))?' blocked':'')+'"></span>').join('')+
    '</div><div class="pieces">'+mapPieces()+'<div id="ghosts"></div></div></div></div></div>'+
    '<footer class="board-footer">'+(place ? '<strong>配置位置</strong><span id="placement-status" class="muted" aria-live="polite"></span>'+
    '<div class="actions">'+button('取消','cancel-place')+button('自動で置く','auto')+
    button('ここに置く','review-position','class="primary"')+'</div>' :
    (room.scene==='B' && room.placed.B && !room.entered && room.viewer==='GM' ?
      '<div class="actions">'+button('戦闘突入','enter','class="primary"')+'</div>' : ''))+
    (room.viewer==='GM' && !place && room.unplaced.length ? '<p class="muted">未配置 '+room.unplaced.length+' 体</p>':'')+
    '</footer></section></div>';
}

function draftRoom() {
  const applied = room.applied;
  const missing = applied ? Math.max(0,applied.info.min - applied.ally.length) : 0;
  const list = rowsForSession().map((entry,i)=>queueEntry(entry,i,button('下書きへ反映','apply-draft','data-id="'+h(entry.id)+'"'))).join('');
  const allies = applied?.ally.map((row,i)=>'<div class="asset"><span>'+h(row.name)+'</span><select aria-label="'+h(row.name)+
    'の担当" data-assignee="'+i+'"><option value="">担当なし</option>'+['GM','PL 1','PL 2','PL 3','PL 4'].map(name=>
    '<option'+(row.assignee===name?' selected':'')+'>'+name+'</option>').join('')+'</select></div>').join('') || '<p class="empty">登録なし</p>';
  const missingOwner = applied?.ally.some(row=>!row.assignee);
  const summary = applied ? '<div class="stack"><div class="room-note">'+badge('敵 '+applied.info.enemies.length+' 体')+
    badge('味方 '+applied.ally.length+' / '+applied.info.min+' 体',missing?'warn':'ok')+'</div>'+
    (missing ? '<p>'+badge('味方不足 '+missing+' 体','warn')+'</p>' : '')+
    (missingOwner ? '<p>'+badge('担当未設定','warn')+'</p>' : '')+
    (room.detail ? '<div class="draft-summary">'+panel('味方・担当',allies)+panel('敵',groupNames(applied.info.enemies)
      .map(name=>'<p>'+h(name)+'</p>').join(''))+'</div><div class="actions">'+
      button('味方を追加','add-ally')+'</div>' : '')+'<div class="actions">'+
      (room.detail?'':button('詳細調整','detail-draft','class="primary"'))+
      (!missing && !missingOwner ? button('戦闘突入を確認','draft-confirm',room.detail?'class="primary"':'') : '')+'</div></div>' :
    '<p class="empty">未反映</p>';
  return '<div class="page-heading"><h2>戦闘専用ルーム</h2></div><div class="draft-grid">'+panel('待機列',list)+
    panel(room.detail ? '詳細調整' : '戦闘下書き',summary)+'</div>';
}

function render() {
  $('#room-state').textContent = {A:'セッション前',B:room.entered?'戦闘突入':room.active?'配置中':'探索中',C:'ラウンド 2 · 終了時',D:'戦闘専用'}[room.scene];
  for (const element of document.querySelectorAll('[data-scene]')) element.setAttribute('aria-pressed', String(element.dataset.scene===room.scene));
  $('#space-setting').hidden = room.viewer!=='GM' || room.scene!=='B';
  if (room.viewer==='PL' && ['A','D'].includes(room.scene)) {
    screen.innerHTML = '<div class="page-heading"><h2>'+ (room.scene==='A'?'セッションルーム':'戦闘専用ルーム') +
      '</h2></div>'+panel('セッション','<p class="empty">開始前</p>');
    return;
  }
  screen.innerHTML = room.scene==='A' ? prep() : room.scene==='D' ? draftRoom() : board();
  if ($('.board-map')) updatePan();
  if (room.active) drawGhosts();
}

function openDialog(title,body,label,next,theme = 'night') {
  if (dialog.open) dialog.close();
  dialog.dataset.theme = theme;
  dialog.innerHTML = '<header class="panel-heading"><h2 id="dialog-title">'+title+
    '</h2></header><div class="panel-body">'+body+'</div><footer>'+
    button('取消','dialog-close')+(label?button(label,'dialog-confirm','class="primary"'):'')+'</footer>';
  dialog.setAttribute('aria-labelledby','dialog-title');
  dialogAction = next;
  dialog.showModal();
}
function validate() {
  const draft = room.draft;
  const info = encounter(draft);
  const countOk = info.enemies.length > 0;
  const assigned = !info.allies.length || !!draft.owner;
  const ok = !!draft.name.trim() && countOk && assigned;
  const results = '<p>'+badge('人数',countOk?'ok':'warn')+' 敵 '+info.enemies.length+' ・味方 '+info.allies.length+
    '</p><p>'+badge('参照',countOk?'ok':'warn')+(countOk?' 選択済み資源に問題なし':' 敵の資源を選択')+'</p><p>'+
    (info.allies.length ? badge('担当',assigned?'ok':'warn')+' '+h(draft.owner || '担当未設定') : badge('担当','ok')+' 味方編成なし')+
    '</p>'+(ok?'':'<p>'+badge('要修正','warn')+' 必須項目を確認</p>');
  openDialog('保存前チェック',results,ok?'保存確定':'',()=>{
    const saved = structuredClone(draft);
    saved.name = saved.name.trim();
    if (draft.id) room.queue = room.queue.map(entry=>entry.id===saved.id?saved:entry);
    else {saved.id=crypto.randomUUID(); room.queue.push(saved);}
    persistQueue();
    room.draft = emptyDraft();
    render();
  },room.theme);
}

function groupNames(rows) {
  const counts = new Map();
  for (const row of rows) counts.set(row.name,(counts.get(row.name)||0)+1);
  return [...counts].map(([name,n])=>name+(n>1?' × '+n:''));
}

function findPositions(anchor,count) {
  const offsets = [[0,0],[-1,0],[1,0],[0,-1],[0,1],[-1,-1],[1,-1],[-1,1],[1,1]];
  const existing = occupied();
  const available = point => inBounds(point) && !existing.has(key(point.x,point.y)) && !blocked(point.x,point.y);
  const footprint = offsets.slice(0,count).map(([x,y])=>({x:anchor.x+x,y:anchor.y+y}));
  const valid = footprint.filter(available);
  const invalid = footprint.filter(point=>!available(point));
  const retained = new Set(valid.map(point=>key(point.x,point.y)));
  const spare = Array.from({length:boardHeight*boardWidth},(_,i)=>({x:i%boardWidth,y:Math.floor(i/boardWidth)}))
    .filter(point=>available(point) && !retained.has(key(point.x,point.y)));
  const distance = point => Math.abs(point.x-anchor.x)+Math.abs(point.y-anchor.y);
  spare.sort((a,b)=>distance(a)-distance(b));
  return {points:[...valid,...spare.slice(0,count-valid.length)],invalid};
}
function startPlace(entry) {
  room.active = {entry,info:encounter(entry),anchor:{x:10,y:4}};
  room.pan = {x:0,y:0};
  render();
  $('.board-viewport').focus({preventScroll:true});
}
function drawGhosts() {
  const {anchor,info} = room.active;
  const total = info.enemies.length + info.allies.length;
  const {points,invalid} = findPositions(anchor,total);
  $('#ghosts').innerHTML = '<span class="cursor-mark" style="'+positionStyle(anchor.x,anchor.y)+'"></span>'+
    invalid.map(point=>'<span class="invalid-tile" style="'+positionStyle(point.x,point.y)+'">×</span>').join('')+
    points.map((point,i)=>'<span class="ghost '+(i<info.enemies.length?'enemy':'ally')+'" style="'+
      positionStyle(point.x,point.y)+'"><i>'+(i<info.enemies.length?'敵':'味')+'</i></span>').join('');
  const shortage = total-points.length;
  const status = $('#placement-status');
  const summary = (anchor.x+1)+' 列・'+(anchor.y+1)+' 行'+(shortage?' · 未配置 '+shortage+' 体':' · 仮置き '+points.length+' 体');
  if(status.textContent!==summary) status.textContent=summary;
}
function updatePan() {
  $('.board-map').style.transform='translate(calc(-50% + '+room.pan.x+'px),calc(-50% + '+room.pan.y+'px))';
}
function setAnchor(point) {
  if (room.active.anchor.x===point.x && room.active.anchor.y===point.y) return;
  room.active.anchor=point;
  drawGhosts();
}
function fromPointer(event) {
  const rect = $('.board-map').getBoundingClientRect();
  return {
    x:Math.max(-1,Math.min(boardWidth,Math.floor((event.clientX-rect.left)/rect.width*boardWidth))),
    y:Math.max(-1,Math.min(boardHeight,Math.floor((event.clientY-rect.top)/rect.height*boardHeight))),
  };
}
function cancelPlace() {
  room.active = null;
  room.pan = {x:0,y:0};
  render();
}
function reviewPosition(automatic = false) {
  if (!room.active) return;
  const {entry,info,anchor} = room.active;
  if(!automatic && !inBounds(anchor)) return;
  const incoming = [...info.enemies,...info.allies];
  const terrain = room.terrain[room.scene];
  const {points} = findPositions(automatic?{x:11,y:3}:anchor,incoming.length);
  const actors = currentActors();
  const keeping = actors.filter(row=>entry.mode==='add' || row.side!=='enemy');
  const removing = actors.filter(row=>!keeping.includes(row));
  const shortage = incoming.length-points.length;
  const column = (label,rows) => '<section><strong>'+label+' '+rows.length+'</strong><ul>'+
    (groupNames(rows).map(name=>'<li>'+h(name)+'</li>').join('') || '<li>なし</li>')+'</ul></section>';
  const diff = '<div class="diff">'+column('維持',keeping)+column('除外',removing)+
    column('追加',incoming)+'</div>';
  const changes = (info.background?'<p>背景　'+(terrain.usesStageBackground?'氷の遺跡':'街道')+' → 氷の遺跡</p>':'')+
    (entry.checked.effects && info.stage ? '<p>フィールド効果　差し替え　'+ h(terrain.effects.join('、') || 'なし')+' → '+h(info.effects.map(row=>row.display_name).join('、') || 'なし')+'</p>':'')+
    (info.avatar ? '<p>ステージアバター　'+h(info.avatar)+'</p>' : '');
  openDialog('登場を確認',diff+changes+(shortage?'<p>'+badge('未配置 '+shortage+' 体','warn')+
    ' '+h(groupNames(incoming.slice(points.length)).join('、'))+'</p>':''),'登場を確定',()=>{
      room.placed[room.scene] = [...keeping,...points.map((point,i)=>i<info.enemies.length ?
        makeEnemy(incoming[i],i,point) : {...incoming[i],...point,side:'ally',current:incoming[i].hp,art:art.ally[i%2]})];
      room.unplaced = incoming.slice(points.length);
      room.done.add(entry.id);
      if(info.stage) terrain.name=info.stage.name;
      if(info.background) terrain.usesStageBackground=true;
      if(entry.checked.effects && info.stage) terrain.effects=info.effects.map(row=>row.display_name);
      cancelPlace();
    });
}

function reinforcement() {
  const units = catalog.units.filter(row=>row.enemy);
  const content = units.map(row=>'<article class="asset" data-lookup="'+h(row.name)+'"><span>'+h(row.name)+'</span>'+
    button('登場','reinforce-unit','data-id="'+h(row.id)+'"')+'</article>').join('');
  openDialog('予定外の増援','<input type="search" data-reinforcement-search aria-label="増援の検索" placeholder="名称で検索">'+content,'',null);
  $('[data-reinforcement-search]').focus();
}

function addAsset(id) {
  const draft=room.draft;
  if(room.type==='unit') {
    const row=draft.extras.find(item=>item.id===id);
    if(row) row.count++;
    else draft.extras.push({id,count:1});
  } else {
    const [field, row] = room.type==='stage' ? ['stageId',stage(id)] : [room.type+'Id',formation(id,room.type)];
    draft[field]=id;
    if(room.type==='stage') draft.enemyId='';
    if(!draft.name) draft.name=row.name;
  }
  render();
}

document.addEventListener('click',event=>{
  const scene = event.target.closest('[data-scene]')?.dataset.scene;
  if(scene) {
    if (scene==='C' && room.placed.B && !room.placed.C) room.terrain.C=structuredClone(room.terrain.B);
    room.scene=scene;
    room.active=null;
    room.pan={x:0,y:0};
    room.unplaced=[];
    render();
    return;
  }
  const control=event.target.closest('[data-action]');
  if(!control || room.viewer!=='GM' || control.disabled) return;
  const {action,id,index,field}=control.dataset;
  const entry=rowsForSession().find(row=>row.id===id);
  if (action==='asset-tab') { room.type=id; room.search=''; render(); }
  if (action==='add-asset') addAsset(id);
  if (action==='clear-asset') { room.draft[field]=''; render(); }
  if (action==='remove-extra') { room.draft.extras.splice(Number(index),1); render(); }
  if (action==='validate') validate();
  if (action==='new-entry') {
    room.draft=emptyDraft(); room.search=''; room.type=room.queue.length?'enemy':'stage'; render(); $('[data-field=name]').focus();
  }
  if (action==='edit-entry') { room.draft=structuredClone(entry); render(); }
  if (action==='remove-entry') { room.queue=room.queue.filter(row=>row.id!==id); persistQueue(); if(room.draft.id===id) room.draft=emptyDraft(); render(); }
  if (action==='appear') startPlace(entry);
  if (action==='cancel-place') cancelPlace();
  if (action==='auto') reviewPosition(true);
  if (action==='review-position') reviewPosition();
  if (action==='enter') {
    openDialog('戦闘突入を確認','<p>配置済みのキャラクターで戦闘を開始</p>','戦闘突入',()=>{room.entered=true; render();});
  }
  if (action==='reinforcement') reinforcement();
  if (action==='reinforce-unit') {
    dialog.close();
    startPlace({...emptyDraft(),id:'reinforcement',mode:'add',extras:[{id,count:1}]});
  }
  if (action==='apply-draft') {
    const info=encounter(entry);
    room.applied={info,ally:info.allies.map(row=>({...row,assignee:entry.owner || ''}))}; room.detail=false; render();
  }
  if (action==='detail-draft') { room.detail=true; render(); }
  if (action==='add-ally') {
    const pool=catalog.units.filter(row=>row.ally);
    const body=pool.map(row=>'<div class="asset"><span>'+h(row.name)+'</span>'+
      button('追加','draft-add-unit','data-id="'+h(row.id)+'"')+'</div>').join('');
    openDialog('味方ユニットを追加',body,'',null);
  }
  if (action==='draft-add-unit') { dialog.close(); room.applied.ally.push({...unit(id),assignee:''}); render(); }
  if (action==='draft-confirm') openDialog('戦闘突入を確認','<p>人数と担当を確認しました。</p>','閉じる',()=>{});
  if (action==='dialog-close' || action==='dialog-confirm') {
    const next=dialogAction;
    dialog.close();
    if(action==='dialog-confirm') next?.();
    else if(room.active) $('.board-viewport').focus({preventScroll:true});
  }
});

document.addEventListener('input',event=>{
  const input=event.target;
  if(input.matches('[data-field]')) room.draft[input.dataset.field]=input.value;
  if(input.matches('[data-option]')) room.draft.checked[input.dataset.option]=input.checked;
  if(input.matches('[data-count]')) {
    const count = Math.max(1,Math.min(150,Number(input.value)||1));
    room.draft.extras[input.dataset.count].count=count;
    $('#enemy-count').textContent=encounter(room.draft).enemies.length;
  }
  if(input.matches('[data-asset-search]')) {room.search=input.value; $('#assets').innerHTML=assetRows();}
  if(input.matches('[data-reinforcement-search]')) for(const row of dialog.querySelectorAll('[data-lookup]')) {
    row.hidden=!row.dataset.lookup.includes(input.value.trim());
  }
});
document.addEventListener('change',event=>{
  const input=event.target;
  if(input.id==='viewer') {if(dialog.open)dialog.close(); room.viewer=input.value; room.active=null; render();}
  if(input.id==='theme') { room.theme=input.value; if(room.scene==='A')render(); }
  if(input.id==='space') {room.tight=input.value==='tight'; render();}
  if(input.matches('[data-count]')) input.value=room.draft.extras[input.dataset.count].count;
  if(input.matches('[data-assignee]')) {room.applied.ally[input.dataset.assignee].assignee=input.value; render();}
});

screen.addEventListener('pointerdown',event=>{
  const viewport=event.target.closest('.board-viewport');
  if(!viewport || event.button!==0) return;
  pointer={id:event.pointerId,x:event.clientX,y:event.clientY,pan:{...room.pan},moved:false};
  viewport.setPointerCapture(event.pointerId);
});
screen.addEventListener('pointermove',event=>{
  if(!event.target.closest('.board-viewport')) return;
  if(pointer?.id===event.pointerId) {
    const dx=event.clientX-pointer.x, dy=event.clientY-pointer.y;
    if(Math.hypot(dx,dy)>7) pointer.moved=true;
    if(pointer.moved) {
      room.pan={x:Math.max(-180,Math.min(180,pointer.pan.x+dx)),y:Math.max(-115,Math.min(115,pointer.pan.y+dy))};
      updatePan();
      return;
    }
  }
  if(room.active && event.pointerType!=='touch') setAnchor(fromPointer(event));
});
screen.addEventListener('pointerup',event=>{
  if(pointer?.id!==event.pointerId) return;
  const moved=pointer.moved;
  pointer=null;
  if(!room.active || moved) return;
  setAnchor(fromPointer(event));
  if(event.pointerType!=='touch') reviewPosition();
});
screen.addEventListener('pointercancel',()=>{pointer=null;});
dialog.addEventListener('cancel',event=>{
  if(room.active) {
    event.preventDefault();
    dialog.close();
    cancelPlace();
  }
});
document.addEventListener('keydown',event=>{
  if(!room.active || dialog.open || event.isComposing) return;
  if(event.key==='Escape') {event.preventDefault(); cancelPlace(); return;}
  if(!event.target.matches('.board-viewport')) return;
  const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
  if(delta) {
    event.preventDefault();
    const {x,y}=room.active.anchor;
    setAnchor({x:Math.max(0,Math.min(boardWidth-1,x+delta[0])),y:Math.max(0,Math.min(boardHeight-1,y+delta[1]))});
  } else if(event.key==='Enter') {event.preventDefault(); reviewPosition();}
});
render();
