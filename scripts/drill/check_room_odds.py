"""Verify forecast badges in the real PvE declaration panel on a disposable DB."""
import argparse
from pathlib import Path
import sys
import uuid

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/ui_room_night_proto'))
from shots import prepare_room, frame_board, post  # noqa: E402

OUT=ROOT/'_local/advantage_shots'
PANEL='#select-resolve-declare-panel-left'


def emit(page,event,payload):
    page.evaluate('([event,payload])=>socket.emit(event,{room:currentRoomName,...payload})',[event,payload])
    page.wait_for_timeout(350)


def select(page,source,target,skill=None):
    page.evaluate('([s,t,k])=>BattleStore.setDeclare({sourceSlotId:s,targetSlotId:t,skillId:k,mode:"editing"})',
                  [source,target,skill])


def forecast(page,source,target):
    return page.evaluate('''([s,t])=>new Promise((resolve,reject)=>socket.timeout(15000).emit('battle_match_odds',{
      room_id:currentRoomName,battle_id:BattleStore.state.battle_id,slot_id:s,target_slot_id:t,skill_ids:['Ps-01','Ps-04']},
      (error,result)=>error?reject(error):resolve(result)))''',[source,target])


def assert_contrast(page):
    ratios=page.evaluate('''() => {
      const rgb=text=>text.match(/[\\d.]+/g).map(Number);
      const lum=c=>c.slice(0,3).map(x=>(x/=255)<=.04045?x/12.92:((x+.055)/1.055)**2.4)
        .reduce((sum,x,i)=>sum+x*[.2126,.7152,.0722][i],0);
      const ratios=[];
      for(const level of ['非常に有利','有利','拮抗','不利','非常に不利']) {
        const chip=document.createElement('span'); chip.className='battle-odds-chip';
        chip.dataset.theme='paper'; chip.dataset.level=level;
        chip.innerHTML=level+'<span class="battle-odds-mark">!</span>'; document.body.appendChild(chip);
        for(const node of [chip,chip.firstElementChild]) {
          const style=getComputedStyle(node), fg=lum(rgb(style.color)), bg=lum(rgb(style.backgroundColor));
          ratios.push([level,(Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05)]);
        }
        chip.remove();
      }
      return ratios;
    }''')
    assert all(ratio>=4.5 for _,ratio in ratios),ratios


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',required=True)
    parser.add_argument('--base',default='http://127.0.0.1:5000')
    args=parser.parse_args()
    copied=Path(args.db).resolve()
    if copied.parent!=(ROOT/'_local/agent_db').resolve() or not copied.is_file():
        parser.error('--db must be an existing disposable DB in _local/agent_db')
    OUT.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome')
        try:
            gm=browser.new_context(base_url=args.base,viewport={'width':1280,'height':800})
            page=gm.new_page(); page.on('pageerror',lambda err:errors.append(str(err)))
            room=prepare_room(page,args.base)
            emit(page,'request_change_mode',{'mode':'battle'})
            emit(page,'request_switch_battle_mode',{'mode':'pve'})
            for i in range(2):
                emit(page,'request_move_character',{'character_id':f'npc-{i}','x':4,'y':1+2*i})
            emit(page,'request_combat_enter',{})
            emit(page,'request_new_round',{})
            page.wait_for_function('window.BattleStore?.state?.timeline.length>=6')
            page.wait_for_timeout(2200)
            battle=page.evaluate('()=>({id:BattleStore.state.battle_id,slots:Object.values(BattleStore.state.slots)})')
            source=next(row['slot_id'] for row in battle['slots'] if row['team']=='ally')
            target=next(row['slot_id'] for row in battle['slots'] if row['team']=='enemy')
            body={'room_id':room,'battle_id':battle['id'],'slot_id':target,'skill_id':'Ps-01',
                  'target':{'type':'single_slot','slot_id':source}}
            emit(page,'battle_intent_commit',body)
            page.wait_for_function('([t,s])=>BattleStore.state.intents[t]?.skill_id==="Ps-01" && BattleStore.state.intents[t]?.target.slot_id===s',arg=[target,source])
            frame_board(page)
            select(page,source,target)
            expect(page.locator(PANEL+' .battle-odds-chip').first).to_be_visible()
            before=forecast(page,source,target)
            assert before.get('odds'),before
            assert not page.locator('.battle-odds-seal').count()
            body['skill_id']='Ps-04'
            emit(page,'battle_intent_commit',body)
            page.wait_for_function('t=>BattleStore.state.intents[t]?.skill_id==="Ps-04"',arg=target)
            after=forecast(page,source,target)
            assert before!=after,(before,after)
            expect(page.locator(PANEL+' .battle-odds-chip').first).to_be_visible()

            player=browser.new_context(base_url=args.base,viewport={'width':1280,'height':800})
            pc=player.new_page(); pc.on('pageerror',lambda err:errors.append(str(err)))
            tag=uuid.uuid4().hex[:8]
            user=post(pc,'/api/register',{'login_name':'odds_'+tag,'password':uuid.uuid4().hex})
            actor_id=next(row['actor_id'] for row in battle['slots'] if row['slot_id']==source)
            emit(page,'request_transfer_character_ownership',{'character_id':actor_id,'new_owner_id':user['user_id']})
            pc.goto(args.base+'/#sessions')
            pc.wait_for_function('window.socket?.connected')
            pc.evaluate("room=>joinRoom(room,null,{role:'Player',gmPin:''})",room)
            pc.wait_for_function('window.BattleStore?.state?.battle_id')
            select(pc,source,target)
            expect(pc.locator(PANEL+' .battle-odds-chip').first).to_be_visible()
            assert forecast(pc,source,target)==after
            assert_contrast(pc)
            pc.screenshot(path=str(OUT/'cards.png'),animations='disabled')
            # Choosing a card shows its cached forecast at once, and the own intent preview that follows
            # must not blank it out and bring it back seconds later (2026-11-19 report).
            pc.evaluate("""()=>{window.__sealRemoved=0;new MutationObserver(rows=>{for(const row of rows)
                for(const node of row.removedNodes) if(node.classList?.contains('battle-odds-seal')) window.__sealRemoved++;
            }).observe(document.body,{childList:true});}""")
            pc.locator(PANEL+' .skill-picker-card[data-skill-id="Ps-01"]').click()
            expect(pc.locator('.battle-odds-seal')).to_be_visible(timeout=300)
            pc.wait_for_function('s=>BattleStore.state.intents[s]?.skill_id==="Ps-01"',arg=source)
            pc.wait_for_timeout(1200)
            assert pc.evaluate('window.__sealRemoved')==0
            seal=pc.locator('.battle-odds-seal')
            assert '戦況予測' in seal.inner_text() and '%' not in seal.inner_text()
            pc.wait_for_timeout(450)
            pc.screenshot(path=str(OUT/'selected.png'),animations='disabled')
            # The floating seal leaves both header actions unobstructed.
            for control in ('#declare-commit-btn-header','#declare-close-btn'):
                assert pc.locator(PANEL+' '+control).evaluate('node=>{const r=node.getBoundingClientRect();return node.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}')
            pc.locator(PANEL+' #declare-minimize-btn').click()
            expect(pc.locator('.battle-odds-seal')).to_have_count(0)
            pc.locator(PANEL+' #declare-minimize-btn').click()
            expect(pc.locator('.battle-odds-seal')).to_be_visible()
            pc.locator(PANEL+' #declare-close-btn').click()
            expect(pc.locator('.battle-odds-seal')).to_have_count(0)
            assert not errors,errors
            print('Verified PvE GM/player badges, opponent re-declaration, compact cards, selected seal, minimize/close and header actions.')
            print('Screenshots:',OUT)
        finally:
            browser.close()


if __name__=='__main__':
    main()
