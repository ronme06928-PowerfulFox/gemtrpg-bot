// Exercise the production account loader/saver; isolate unrelated form rendering.
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const html = fs.readFileSync('CharaCreator/GEMDICEBOT_CharaCreator.html', 'utf8');
const start = html.indexOf('let CURRENT_OWNED_CHARACTER_ID =');
const end = html.indexOf('function restoreFromCommands', start);
if (start < 0 || end < start) throw new Error('Account functions not found');
const nodes = new Map();
for (const id of ['account-save-msg', 'json-output', 'p-exp', 'p-exp-scenario', 'char-origin', 'char-hometown']) {
  nodes.set(id, {value: '', textContent: '', style: {}});
}
const fieldIds = {'経験': 'p-exp', 'シナリオ経験': 'p-exp-scenario', '出身': 'char-origin', 'ボーナス': 'char-hometown'};
let data;
const requests = [], confirmations = [];
const context = {
  document: {getElementById(id) {return nodes.get(id);}},
  async fetch(url, options = {}) {
    if (!options.method) return {ok: true, json: async () => ({character: input.character})};
    requests.push({url, method: options.method, payload: JSON.parse(options.body)});
    return {ok: true, json: async () => ({character: input.character})};
  },
  applyCharacterJsonToForm(payload) {
    data = structuredClone(payload.data);
    for (const param of data.params || []) {
      if (fieldIds[param.label]) nodes.get(fieldIds[param.label]).value = param.value;
    }
  },
  calculateStats() {},
  updateJSON() {
    for (const [label, id] of Object.entries(fieldIds)) {
      let param = (data.params || []).find(row => row.label === label);
      if (!param) {param = {label}; (data.params ||= []).push(param);}
      param.value = String(nodes.get(id).value);
    }
    nodes.get('json-output').value = JSON.stringify({kind: 'character', data});
  },
  confirm(message) {confirmations.push(message); return input.confirmSave !== false;},
  alert(message) {throw new Error(message);},
};
vm.createContext(context);
vm.runInContext(html.match(/function getBonusOriginId\(\) \{[\s\S]+?\n        \}/)[0], context);
vm.runInContext(html.slice(start, end), context);
(async () => {
  await context.loadOwnedCharacterFromAccount(input.character.id);
  const loadMessage = nodes.get('account-save-msg').textContent;
  await context.saveToAccount();
  process.stdout.write(JSON.stringify({requests, confirmations, loadMessage,
    base: Number(nodes.get('p-exp').value), scenario: Number(nodes.get('p-exp-scenario').value)}));
})().catch(error => {console.error(error); process.exitCode = 1;});
