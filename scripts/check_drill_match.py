"""Benchmark exact estimates and compare them to the real F03 CLI, using JSON only."""
import argparse
from collections import Counter
import json
import logging
import os
import re
from pathlib import Path
import subprocess
import sys
from time import perf_counter
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['GEMTRPG_SKIP_IMPORT_STARTUP'] = '1'
logging.disable(logging.CRITICAL)

from extensions import all_skill_data, all_buff_data  # noqa: E402
from manager.cache_paths import load_json_cache, SKILLS_CACHE_FILE, BUFF_CATALOG_CACHE_FILE  # noqa: E402
from manager.drill.match import calculate_match  # noqa: E402
from manager.drill.distribution import dice_distribution  # noqa: E402
from manager.game_logic import calculate_skill_preview  # noqa: E402
from manager.battle.skill_rules import _extract_rule_data_from_skill  # noqa: E402


def character(key, team, correction):
    return {'id':key, 'name':key, 'type':team, 'hp':1, 'maxHp':1, 'mp':10, 'maxMp':10,
            'x':0, 'y':0, 'is_escaped':False, 'states':[], 'special_buffs':[], 'flags':{'auto_skill_select':True,'auto_target_select':True},
            'commands':all_skill_data['E-00']['チャットパレット'],
            'params':[{'label':key,'value':value} for key,value in [
                ('物理補正',correction), ('魔法補正',correction), ('敏捷',6), ('行動回数',1)]]}


def benchmark(actor, target):
    candidates=[]
    for key, skill in all_skill_data.items():
        try:
            preview=calculate_skill_preview(actor,target,skill,rule_data=_extract_rule_data_from_skill(skill))
            counts,_=dice_distribution(preview['final_command'])
            if len(counts)**2 <= 65536:
                candidates.append((sum(int(n) for n in re.findall(r'(\d+)d',preview['final_command'])),len(counts),key,preview['final_command']))
        except (ValueError,TypeError,AttributeError,ArithmeticError):
            continue
    dice_count,width,key,command=max(candidates)
    elapsed=[]
    for _ in range(5):
        start=perf_counter()
        calculate_match(actor,target,key,key)
        elapsed.append((perf_counter()-start)*1000)
    # Stress the supported limit too, rather than measuring only today's small cache.
    all_skill_data['DRILL-BENCH']={'id':'DRILL-BENCH','分類':'物理','tags':['攻撃'],
        '基礎威力':0,'ダイス威力':'16d16','チャットパレット':'0+16d16',
        '特記処理':'{"schema":"skill_json_rule_v2","effects":[]}'}
    try:
        start=perf_counter()
        calculate_match(actor,target,'DRILL-BENCH','DRILL-BENCH')
        stress_ms=(perf_counter()-start)*1000
    finally:
        del all_skill_data['DRILL-BENCH']
    return {'cache_skill':key,'command':command,'dice_count':dice_count,'width':width,
            'median_ms':sorted(elapsed)[2],'max_ms':max(elapsed),
            'stress':'16d16 vs 16d16 (58081 power pairs)','stress_ms':stress_ms}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=int,default=5000)
    args=parser.parse_args()
    if not 1 <= args.runs <= 20000:
        parser.error('--runs must be 1..20000')
    all_skill_data.update(load_json_cache(SKILLS_CACHE_FILE))
    all_buff_data.update(load_json_cache(BUFF_CATALOG_CACHE_FILE))
    actor,target=character('A1','ally',6),character('E1','enemy',4)
    estimate=calculate_match(actor,target,'E-00','E-00')
    timing=benchmark(actor,target)
    folder=(ROOT/'_local'/'drill_check').resolve()
    assert folder.parent == (ROOT/'_local').resolve()
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/('cli-'+uuid.uuid4().hex+'.json')
    state={'round':0,'battle_mode':'pve','play_mode':'normal','characters':[actor,target],'timeline':[], 'battle_state':{
        'battle_id':'drill-check','round':0,'phase':'round_end','slots':{},'timeline':[],
        'intents':{},'redirects':[], 'resolve':{'mass_queue':[],'single_queue':[],
                                           'resolved_slots':[],'trace':[]}}}
    path.write_text(json.dumps(state,ensure_ascii=False),encoding='utf-8')
    try:
        run=subprocess.run([sys.executable,str(ROOT/'scripts'/'simulate_battle.py'),
            '--input',str(path),'--auto-ally-intents','--roll-mode','random','--max-rounds','1',
            '--runs',str(args.runs),'--seed','6301','--json'],cwd=ROOT,
            capture_output=True,text=True,encoding='utf-8',timeout=600,
            env={**os.environ,'PYTHONIOENCODING':'utf-8'})
        if run.returncode:
            raise RuntimeError(run.stderr)
        payload=json.loads(run.stdout)
    finally:
        path.unlink()
    counts=Counter(row['result'] for row in payload.get('runs',[payload]))
    assert not (counts.keys()-{'ally_win','enemy_win','in_progress'}),counts
    observed={'win':counts['ally_win']/args.runs,'draw':counts['in_progress']/args.runs,
              'lose':counts['enemy_win']/args.runs}
    rate=observed['win']+observed['draw']/2
    print(json.dumps({'runs':args.runs,'skill_pair':['E-00','E-00'],
        'corrections':[6,4], 'exact':estimate['probabilities'],'cli':observed,
        'exact_win_rate':estimate['win_rate'],'cli_win_rate':rate,
        'difference_percentage_points':(rate-estimate['win_rate'])*100,
        'benchmark':timing},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
