import { sceneSamples, characters } from '../fx_gallery/samples.mjs';

const copy = value => JSON.parse(JSON.stringify(value));
const skillIds = {
  'ally-win': ['Pb-01', 'E-04'],
  'enemy-ko': ['Ps-01', 'E-05'],
  'long-names': ['Ms-06', 'Pb-10'],
  'one-sided': ['Pb-04', null],
  summation: ['E-11', 'Ps-01'],
  fizzle: ['Pp-06', 'E-04'],
  silhouette: ['Pb-07', 'Ps-03'],
  'hard-attack': ['E-23', 'Pb-01'],
  'mass-individual': ['E-33', 'Ps-01'],
};
function fromGallery(source, id, label, order) {
  const sample = copy(sceneSamples.find(row => row.id === source));
  sample.id = id;
  sample.label = label;
  sample.skillIds = { attacker: skillIds[id][0], defender: skillIds[id][1] };
  sample.step.attackerSkillId = sample.skillIds.attacker;
  sample.step.defenderSkillId = sample.skillIds.defender;
  delete sample.step.attackerSkillNameHint;
  delete sample.step.defenderSkillNameHint;
  sample.state.characters = ['a', 'd', 'e', 'f'].map((key, i) => ({ ...characters[order[i]], id: key }));
  return sample;
}
const allyWin = fromGallery('many-lines', 'ally-win', '01 · 味方勝利 / 戦慄殺到と破裂', [0, 1, 2, 3]);
allyWin.step.applied.fired_effects = [{ term_id: 'W-07', name: '戦慄殺到', actor_id: 'a', target_id: 'd',
  results: [{ name: 'MP', delta: -5 }] }];
allyWin.step.applied.statuses = [{ target_id: 'd', name: '破裂', delta: 3 }, { target_id: 'd', name: '混乱', before: 0, after: 1 }];
const enemyKo = fromGallery('fear-ko', 'enemy-ko', '02 · 敵勝利 / 味方が戦闘不能', [3, 2, 1, 0]);
enemyKo.step.outcome = 'defender_win';
enemyKo.step.rolls.power_a = 4;
enemyKo.step.rolls.power_b = 8;
enemyKo.step.applied = { damage: [{ target_id: 'a', hp: 12, hp_after: 0, source: 'dice' }], statuses: [], fired_effects: [] };
const longNames = fromGallery('many-lines', 'long-names', '03 · 長い名前 / 長いスキル文章', [1, 3, 0, 2]);
longNames.state.characters[0].name = '夜明けを待つ蒼天の誓いを継ぎし放浪の剣士';
longNames.state.characters[1].name = '星々の記憶と古き王国の意志を守る最後の騎士';
longNames.nameOverrides = {
  attacker: '幾千の夜を越え暁の彼方へと捧ぐ終わりなき剣',
  defender: '忘れ去られた星々の祈りを抱く永遠なる防壁',
};
const oneSided = fromGallery('rupture', 'one-sided', '04 · 一方攻撃 / 破裂爆発', [3, 1, 0, 2]);
const summation = fromGallery('summation', 'summation', '05 · 広域-合算 / 3人被弾・1人戦闘不能', [2, 0, 3, 1]);
const fizzle = fromGallery('fear-ko', 'fizzle', '06 · 不発', [0, 2, 1, 3]);
fizzle.step.kind = 'fizzle';
fizzle.step.outcome = 'fizzle';
fizzle.step.applied = { damage: [], statuses: [], fired_effects: [] };
const silhouette = fromGallery('rupture', 'silhouette', '07 · 立ち絵なし / シルエット', [2, 3, 0, 1]);
silhouette.step.kind = 'clash';
silhouette.state.characters[0].image = null;
silhouette.state.characters[0].name = '影の旅人';
const hard = fromGallery('rupture', 'hard-attack', '08 · 強硬攻撃', [0, 2, 3, 1]);
hard.step.kind = 'hard_attack';
const individual = fromGallery('many-lines', 'mass-individual', '09 · 広域-個別', [1, 0, 2, 3]);
individual.step.kind = 'mass_individual';
// 人数の多い広域-合算。立ち絵は4枚を使い回し、1人は立ち絵なしにする。
function crowd(id, label, count, koIndex) {
  const sample = fromGallery('summation', id, label, [2, 0, 3, 1]);
  const extra = Array.from({ length: count - 3 }, (_, i) => ({ ...characters[i % 4], id: `p${i}`,
    name: `${characters[i % 4].name}・${i + 2}`, image: i === 1 ? null : characters[i % 4].image }));
  sample.state.characters.push(...extra);
  for (const c of extra) sample.state.slots[`s${c.id}`] = { actor_id: c.id };
  const ids = ['d', 'e', 'f', ...extra.map(c => c.id)];
  sample.step.participants = ids.map(c => `s${c}`);
  sample.step.rolls.defender_powers = Object.fromEntries(ids.map((c, i) => [`s${c}`, 3 + (i * 5) % 7]));
  sample.step.rolls.defender_sum = Object.values(sample.step.rolls.defender_powers).reduce((a, b) => a + b, 0);
  sample.step.damageEvents = ids.map((target_id, i) => ({ target_id, hp: 4 + i % 5,
    hp_after: i === koIndex ? 0 : 10, damage_type: 'mass_summation_delta' }));
  return sample;
}
skillIds['summation-5'] = skillIds['summation-8'] = skillIds.summation;
const crowd5 = crowd('summation-5', '10 · 広域-合算 / 5人（重ねて並べる）', 5, 3);
const crowd8 = crowd('summation-8', '11 · 広域-合算 / 8人（5人＋まとめ）', 8, 1);
export const samples = [allyWin, enemyKo, longNames, oneSided, summation, fizzle, silhouette, hard, individual, crowd5, crowd8];
