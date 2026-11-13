from tests.test_catalog_skill_editor import run_node


def test_card_order_preferences_cache_and_stale_response():
    run_node(r"""
vm.runInContext(fs.readFileSync('static/js/master_data/power.js','utf8'),context);
const power=window.CatalogPower, local=new Map();
window.localStorage={getItem:k=>local.get(k),setItem:(k,v)=>local.set(k,v)};
const cache=JSON.parse(fs.readFileSync('data/cache/skills_cache.json','utf8'));
const payload={...cache['Ps-04'],'特記処理':{}};
const other={...cache['Mb-13'],'特記処理':{}};
let pending=[],requests=[];
const body={innerHTML:''};
const card={isConnected:true,querySelector:()=>body};
const root={querySelector:()=>card};
const controller=power.mount(root,(payload,params)=>{
 requests.push(params);
 return new Promise(resolve=>pending.push(resolve));
});
const settle=()=>new Promise(resolve=>setTimeout(resolve,10));
const result=(min=8,avg=10.5,max=13,dice='7+1d6')=>({min,avg,max,dice,rules:[{text:null,apply_to:'基礎威力',in_baseline:false}]});
let html=controller.render(payload,model.palette(payload,'Ps-04'),'skill:Ps-04:1',schemas);
assert.match(html,/補正を適用/);
assert.match(html,/cat-power-params" hidden/);
assert.match(html,/value="5"/);
const composed=model.preview(payload,{power:html});
assert.ok(composed.indexOf('ゲームでの見え方') < composed.indexOf('威力の見込み'));
assert.ok(composed.indexOf('威力の見込み') < composed.indexOf('効果の説明'));
await settle();assert.equal(requests.length,1);pending.shift()(result());await settle();
assert.match(body.innerHTML,/<dd>10.5<\/dd>/);assert.match(body.innerHTML,/JSON を見る/);
controller.render(payload,model.palette(payload,'Ps-04'),'skill:Ps-04:1',schemas);await settle();assert.equal(requests.length,1);
const box={hidden:true};
const toggle={checked:true,dataset:{powerToggle:''},closest:()=>({querySelector:()=>box})};
assert.equal(controller.input(toggle),true);
assert.equal(box.hidden,false);
await settle();assert.equal(requests.at(-1).物理補正,5);
controller.render(other,model.palette(other,'Mb-13'),'skill:Mb-13:1',schemas);await settle();
const old=pending.shift(),fresh=pending.shift();fresh(result(6,7.5,9));await settle();old(result(9,13.5,18));await settle();
assert.match(body.innerHTML,/<dd>7.5<\/dd>/);assert.doesNotMatch(body.innerHTML,/<dd>13.5<\/dd>/);
const changed={...payload,ダイス威力:'+2d6'};
assert.match(controller.render(changed,model.palette(changed,'Ps-04'),null,schemas),/チャットパレットが項目と違います/);
changed.チャットパレット=model.palette(changed,'Ps-04');
assert.doesNotMatch(controller.render(changed,model.palette(changed,'Ps-04'),null,schemas),/チャットパレットが項目と違います/);
const noCorrection={...cache['E-26'],'特記処理':{}};
assert.doesNotMatch(controller.render(noCorrection,model.palette(noCorrection,'E-26'),null,schemas),/補正を適用<\/label>/);
controller.destroy();
const restored=power.mount(root,()=>Promise.resolve(result()));
assert.match(restored.render(other,model.palette(other,'Mb-13'),'skill:Mb-13:1',schemas),/data-power-toggle checked/);
restored.destroy();
""")
