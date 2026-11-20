"""Exercise the real private practice room on an explicitly selected disposable DB."""
import argparse
from pathlib import Path
import sqlite3
import uuid

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'_local/practice_room_shots'


def api(page,path,body=None):
    response=page.request.post(path,data=body) if body is not None else page.request.get(path)
    assert response.ok,(path,response.status,response.text())
    return response.json()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',required=True)
    parser.add_argument('--base',default='http://127.0.0.1:5000')
    args=parser.parse_args()
    copied=Path(args.db).resolve()
    if copied.parent!=(ROOT/'_local/agent_db').resolve() or not copied.is_file():
        parser.error('--db must select an existing disposable DB in _local/agent_db')
    OUT.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome')
        try:
            staff=browser.new_context(base_url=args.base)
            author=staff.new_page()
            tag=uuid.uuid4().hex[:8]
            who=api(author,'/api/register',{'login_name':'practice_author_'+tag,'password':uuid.uuid4().hex})
            with sqlite3.connect(copied) as connection:
                connection.execute('UPDATE users SET is_catalog_author=1 WHERE id=?',(who['user_id'],))
            unit=api(author,'/api/units/unit',{'visibility':'public','payload':{
                'name':'演習の番兵','allow_ally':False,'allow_enemy':True,'marks':['known'],
                'hp':80,'mp':20,'image':'/static/images/characters/人狼型シュラーカー.png',
                'params':[{'label':'速度','value':2},{'label':'五感','value':2},{'label':'物理補正','value':3}],
                'skills':[{'id':'E-00','name':'番兵の一撃'}]}})['entry']
            staff.close()
            context=browser.new_context(base_url=args.base,viewport={'width':1280,'height':800})
            page=context.new_page(); page.on('pageerror',lambda error:errors.append(str(error)))
            user=api(page,'/api/register',{'login_name':'practice_player_'+tag,'password':uuid.uuid4().hex})
            skills=api(page,'/api/get_skill_data')
            hero=api(page,'/api/owned_characters',{'kind':'character','data':{
                'name':'演習の冒険者','image':'/static/images/characters/女冒険者.png',
                'status':[{'label':'HP','value':40,'max':40},{'label':'MP','value':20,'max':20},{'label':'FP','value':8,'max':8}],
                'params':[{'label':'速度','value':2},{'label':'五感','value':2},{'label':'物理補正','value':3}],
                'commands':'\n'.join(skills[key]['チャットパレット'] for key in ('Ps-00','Ps-01'))}})['character']
            page.goto(args.base+'/#drill'); page.reload()
            page.locator('[data-side="actor"] [data-source]').select_option('owned')
            page.locator('[data-side="actor"] [data-record]').select_option(hero['id'])
            page.locator('[data-side="target"] [data-source]').select_option('unit')
            page.locator('[data-side="target"] [data-record]').select_option(unit['entry_id'])
            expect(page.locator('.drill-start')).to_be_enabled()
            def add_skill(side, key):
                field=page.locator(f'[data-side="{side}"]')
                field.locator('[data-add-search]').fill(key)
                field.locator('[data-add-picker]').select_option(key)
                field.locator('[data-add-skill]').click()
                expect(field.locator('[data-remove-skill="'+key+'"]')).to_be_visible()
                assert not field.locator('[data-add-picker] option[value="'+key+'"]').count()
            add_skill('actor','Pb-00')
            add_skill('actor','Pp-00')
            # Choosing a different source retains additions, including on a blank character.
            page.locator('[data-side="actor"] [data-source]').select_option('blank')
            page.locator('[data-side="actor"] [data-name]').fill('練習の冒険者')
            expect(page.locator('[data-side="actor"] [data-remove-skill="Pb-00"]')).to_be_visible()
            add_skill('target','Ps-00')
            page.screenshot(path=str(OUT/'skills.png'),animations='disabled')
            assert not page.locator('.drill input[type="number"]').count()
            page.locator('.drill-start').click()
            page.wait_for_function('window.BattleStore?.state?.round===1 && Object.keys(BattleStore.state.slots).length>=2')
            expect(page.locator('.practice-controls')).to_be_visible()
            # 駒は真ん中の列に置き、2人の真ん中を画面の中央に合わせる。
            page.wait_for_timeout(600)
            gap=page.evaluate('''() => {
              const v=document.querySelector('#map-viewport').getBoundingClientRect();
              const r=[...document.querySelectorAll('#map-token-layer .map-token')].map(t=>t.getBoundingClientRect());
              const x=(Math.min(...r.map(b=>b.left))+Math.max(...r.map(b=>b.right)))/2, y=(Math.min(...r.map(b=>b.top))+Math.max(...r.map(b=>b.bottom)))/2;
              return [Math.abs(x-(v.left+v.width/2)), Math.abs(y-(v.top+v.height/2)), r.length];
            }''')
            assert gap[2]==2 and gap[0]<40 and gap[1]<40,gap
            room=page.evaluate('currentRoomName')
            assert page.evaluate('battleState.characters.find(c=>c.id==="practice_0").commands.includes("【Pb-00 ")')
            assert page.evaluate('battleState.characters.find(c=>c.id==="practice_1").commands.includes("【Ps-00 ")')
            assert room.startswith('__practice__:')
            assert page.locator('#header-attribute').inner_text()=='GM'
            assert api(page,'/list_rooms')['rooms']==[]
            page.evaluate('socket.disconnect()')
            expect(page.locator('.practice-controls')).to_contain_text('再接続しています')
            page.evaluate('socket.connect()')
            page.wait_for_function('socket.connected && document.querySelector("[data-practice=reset]") && window.BattleStore?.state?.round===1')
            page.locator('.app-loading').wait_for(state='hidden')
            assert page.evaluate('currentRoomName')==room
            page.locator('[data-practice="mode"][data-mode="auto"]').click()
            page.wait_for_function('Object.values(BattleStore.state.intents).some(row=>row.skill_id && row.committed)')
            def select_source():
                page.evaluate('''() => {
                  const slots=Object.values(BattleStore.state.slots);
                  const a=slots.find(s=>s.actor_id==='practice_0'),b=slots.find(s=>s.actor_id==='practice_1');
                  BattleStore.setDeclare({sourceSlotId:a.slot_id,targetSlotId:b.slot_id,skillId:null,mode:'editing'});
                }''')
            select_source()
            page.locator('.skill-picker-card[data-skill-id="Pb-00"]').click()
            expect(page.locator('.battle-odds-seal')).to_be_visible()
            page.wait_for_timeout(450)
            page.screenshot(path=str(OUT/'added_declare.png'),animations='disabled')
            # 自動の宣言は足したスキルも選ぶので、E-00 を選んだときだけ付けた名前を確かめる。
            foe_named=page.evaluate('Object.values(BattleStore.state.intents).some(row=>row.skill_id==="E-00" && row.committed)')
            foe_panel=page.locator('#select-resolve-declare-panel-right').inner_text()
            assert '殴る' not in foe_panel and (not foe_named or '番兵の一撃' in foe_panel),foe_panel
            page.locator('#declare-commit-btn-header').click()
            expect(page.locator('#sr-resolve-confirm-btn')).to_be_enabled()
            page.locator('#sr-resolve-confirm-btn').click()
            page.locator('.resolve-flow-next-btn').wait_for()
            # 敵ユニットに付けた名前が、解決の表示でも元の名前（殴る）の代わりに出る。
            if foe_named: expect(page.locator('#resolve-flow-panel')).to_contain_text('番兵の一撃')
            assert '殴る' not in page.locator('#resolve-flow-panel').inner_text()
            # Use the normal presentation buttons until the existing completion path starts round 2.
            for _ in range(20):
                if page.evaluate('BattleStore.state.round>=2'): break
                next_button=page.locator('.resolve-flow-next-btn')
                if next_button.count() and next_button.is_visible() and next_button.is_enabled(): next_button.click()
                page.wait_for_timeout(700)
            page.wait_for_function('BattleStore.state.round===2 && BattleStore.state.phase==="select"',timeout=20000)
            assert page.evaluate('battleState.characters.some(c=>c.hp<c.maxHp)')
            page.locator('[data-practice="reset"]').click()
            page.wait_for_function('BattleStore.state.round===1 && battleState.characters.find(c=>c.id==="practice_1").hp===80')
            select_source()
            page.locator('.skill-picker-card[data-skill-id="Pb-00"]').click()
            expect(page.locator('.battle-odds-seal')).to_be_visible()
            page.locator('[data-practice="detail"]').click()
            expect(page.locator('.practice-detail .drill-verdict')).to_be_visible()
            assert not page.locator('.practice-detail [data-source]').count()
            assert not page.locator('.practice-detail input[type="number"]').count()
            page.locator('.practice-detail [data-side="actor"] [data-skill]').select_option('Pb-00')
            expect(page.locator('.practice-detail .drill-verdict')).to_be_visible()
            assert page.locator('.practice-detail [data-side="target"] [data-skill] option[value="Ps-00"]').count()==1
            page.locator('.practice-detail-close').click()
            page.set_viewport_size({'width':1280,'height':800})
            assert not page.locator('.practice-detail').count()
            page.locator('[data-practice="mode"][data-mode="manual"]').click()
            page.wait_for_function('battleState.battle_mode==="pvp"')
            page.locator('[data-practice="choose"]').click()
            page.wait_for_url('**/#drill')
            assert page.locator('[data-side="actor"] [data-source]').input_value()=='blank'
            assert page.locator('[data-side="target"] [data-record]').input_value()==unit['entry_id']
            for side,keys in [('actor',['Pb-00','Pp-00']),('target',['Ps-00'])]:
                for key in keys:
                    expect(page.locator(f'[data-side="{side}"] [data-remove-skill="{key}"]')).to_be_visible()
            expect(page.locator('.drill-start')).to_be_enabled()
            page.locator('.drill-start').click()
            expect(page.locator('.practice-controls')).to_be_visible()
            page.evaluate("leaveRoomTo('menu')")
            page.wait_for_url('**/#menu')
            assert not page.locator('.practice-controls').count()
            assert api(page,'/list_rooms')['rooms']==[]
            with sqlite3.connect(copied) as connection:
                assert connection.execute('SELECT count(*) FROM rooms').fetchone()[0]==0
                assert connection.execute('SELECT count(*) FROM catalog_encounters WHERE user_id=?',(user['user_id'],)).fetchone()[0]==0
            assert not errors,errors
            print('Verified player additions: blank actor with two skills, known unit with one, real declaration/odds/match, next round, reset/detail/reselection retain additions, no Room/Encounter rows.')
            print('Screenshots:',OUT)
        finally:
            browser.close()


if __name__=='__main__':
    main()
