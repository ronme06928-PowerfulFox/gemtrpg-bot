(function () {
  function readable(masters, extra) {
    const data = window.EncyclopediaData.build(masters, extra, false);
    return Object.fromEntries(Object.entries(data.rowsByKind).map(([kind,rows]) => [kind,rows.filter(row => row.met)]));
  }
  function heldSkills(character, skills) {
    const ids = new Set([...String(character.commands || '').matchAll(/[【\[]\s*([A-Za-z0-9_-]+)(?=[\s\]】])/g)].map(match => match[1]));
    return skills.filter(row => ids.has(row.id));
  }
  function blank(name) {
    return {name,hp:0,maxHp:0,mp:0,maxMp:0,params:[],states:[],special_buffs:[],commands:''};
  }
  async function json(path, options = {}) {
    const response = await fetchWithSession(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `読み込めませんでした（${response.status}）`);
    return data;
  }
  function post(path, body, signal) {
    return json(path, {method:'POST',signal,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  }
  window.DrillData = {readable,heldSkills,blank,json,post};
})();
