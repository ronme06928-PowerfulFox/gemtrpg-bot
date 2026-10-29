import { resolveOutcomeWindow } from '../../static/js/battle/components/resolve_flow_fx.js';

const koDuration = resolveOutcomeWindow({ selfDestructed: ['sample'] });
// 正規化済みtraceはPR4のテストと同じ形。見本の値はこのファイルに集約する。
const sample = (id, effect, label, params = {}, anchor = '.side.defender .name') =>
  ({ id, effect, label, params, anchor, level: 'normal' });

export const effectSamples = [
  sample('float-damage', 'float-text', 'HP −9', { text: '−9', tone: 'damage' }),
  sample('float-heal', 'float-text', 'HP +12', { text: '+12', tone: 'heal' }),
  sample('round', 'round-banner', 'ROUND 3', { text: 'ROUND 3' }, '.resolve-flow-card'),
  sample('power', 'power-roll', '威力 12 / 2d6+3（5〜15）', { text: '12', range: { min: 5, max: 15 } }, '.actual.attacker'),
  sample('power-unknown', 'power-roll', '合算 23 / 幅不明', { text: '23' }, '.actual.attacker'),
  sample('clash', 'clash-flash', '打ち合い', {}, '.vs'),
  sample('shade-win', 'clash-shade', '勝った側', { winner: true }, '.resolve-flow-background.attacker'),
  sample('shade-lose', 'clash-shade', '負けた側', { winner: false }, '.resolve-flow-background.defender'),
  ...['flash', 'slash', 'strike', 'pierce'].flatMap(kind =>
    ['small', 'medium', 'large'].flatMap(tier => [1, -1].flatMap(direction =>
      ['hit', 'wide', 'draw'].map(mode => sample(
        `${kind}-${tier}-${direction}-${mode}`, `attack-${kind}`,
        `${tier} / ${direction === 1 ? '左→右' : '右→左'} / ${mode}`,
        { tier, direction, mode, tone: mode === 'draw' ? 'neutral' : direction === 1 ? 'enemy' : 'ally' },
        mode === 'draw' ? '.vs' : mode === 'wide' ? '.summation-chips'
          : `.resolve-flow-background.${direction === 1 ? 'defender' : 'attacker'}`,
      ))))),
  sample('impact', 'impact-flash', '大の一撃（派手で表示）', {}, '.resolve-flow-card'),
  ...['ally', 'enemy', 'extra'].flatMap(tone => ['small', 'medium', 'large'].map(shake =>
    sample(`damage-${tone}-${shake}`, 'resolve-damage', `${tone} / 揺れ ${shake}`, { amount: 15, tone, shake }))),
  ...Object.entries({ 出血: 'bleed', 破裂: 'rupture', 亀裂: 'fissure', 荊棘: 'thorns', 戦慄: 'fear', 蓄力: 'chikuryoku', 凝魔: 'gyoma' })
    .map(([label, icon]) => sample(`damage-${icon}`, 'resolve-damage', `${label}のアイコン`, {
      amount: 5, tone: 'extra', shake: 'medium', label, icon: `/static/images/${icon}.png`,
    })),
  ...['enemy', 'ally', 'self'].map(tone => sample(`effect-${tone}`, 'effect-band', `戦慄殺到 / ${tone}`, {
    duration: 4.5, groups: [{ lines: [
      { kind: 'title', text: '戦慄殺到', tone },
      { kind: 'result', text: 'MP', delta: -5, tone },
      { kind: 'result', text: '混乱', delta: null, tone },
    ] }],
  })),
  sample('band-heights', 'effect-band', '付与 → 戦慄殺到 → 破裂爆発 · まとまりで流す', {
    duration: 4.6, groups: [
      { lines: [{ kind: 'result', text: '破裂', delta: 3, icon: '/static/images/rupture.png', tone: 'enemy' },
        { kind: 'result', text: '出血', delta: 2, icon: '/static/images/bleed.png', tone: 'enemy' }] },
      { lines: [{ kind: 'title', text: '戦慄殺到', tone: 'ally' }, { kind: 'result', text: 'MP', delta: -5, tone: 'ally' },
        { kind: 'result', text: '混乱', delta: null, tone: 'ally' }] },
      { lines: [{ kind: 'title', text: '破裂爆発', tone: 'enemy' }] },
      { lines: [{ kind: 'title', text: '再使用', tone: 'self' }] },
    ],
  }),
  sample('confusion', 'effect-band', '混乱（結果なし）', { duration: 4.5,
    groups: [{ lines: [{ kind: 'title', text: '混乱', tone: 'ally' }] }] }),
  sample('ko-hit', 'ko-shatter', '戦闘不能', { mode: 'hit', duration: koDuration }, '.resolve-flow-background.defender'),
  ...['light', 'rich'].map(level => ({ ...sample(`ko-hit-${level}`, 'ko-shatter', `背景全体のガラス / ${level === 'light' ? '軽め' : '派手'}`,
    { mode: 'hit', duration: koDuration }, '.resolve-flow-background.defender'), level })),
  ...[{ id: 'ko-wide', label: '横長の背景 590×400', width: 590, height: 400 },
    { id: 'ko-tall', label: '縦長の背景 330×420', width: 330, height: 420 }].map(size => ({
      ...sample(size.id, 'ko-shatter', size.label, { mode: 'hit', duration: koDuration }, '.resolve-flow-background.defender'),
      previewSize: { width: size.width, height: size.height },
    })),
  // 割れ方はキャラのIDを種にした疑似乱数で決まる。種を変えると割れ方が変わる（計画52 §6.6-8）。
  ...['人狼型シュラーカー', '小人型シュラーカー', '女冒険者'].map((targetId, i) =>
    sample(`ko-seed-${i + 1}`, 'ko-shatter', `割れ方の違い ${i + 1}（${targetId}）`,
      { mode: 'hit', duration: koDuration, targetId }, '.resolve-flow-background.defender')),
  sample('ko-chip', 'ko-shatter', '参加者の戦闘不能', { mode: 'chip', duration: koDuration }, '.participant-chip[data-actor-id="e"] .resolve-flow-portrait-inline'),
  sample('chat', 'chat-dice', '2d6+5 → 13', {
    text: '13', range: { min: 7, max: 17 },
  }, '.chat-total'),
  sample('chat-unknown', 'chat-dice', '合計 18 / 式不明', { text: '18' }, '.chat-total'),
];

export const characters = [
  { id: 'a', name: 'リオ', type: 'ally', image: '/static/images/characters/女冒険者.png' },
  { id: 'd', name: '人狼型シュラーカー', type: 'enemy', image: '/static/images/characters/人狼型シュラーカー.png' },
  { id: 'e', name: '小人型シュラーカー', type: 'enemy', image: '/static/images/characters/小人型シュラーカー.png' },
  { id: 'f', name: 'カイ', type: 'ally', image: '/static/images/characters/男冒険者.png' },
];
const state = { characters, slots: Object.fromEntries(characters.map(c => [`s${c.id}`, { actor_id: c.id }])) };
const step = (overrides = {}) => ({
  kind: 'clash', outcome: 'attacker_win', attackerActorId: 'a', defenderActorId: 'd',
  attackerSlotId: 'sa', defenderSlotId: 'sd', attackerSkillId: 'S-01', defenderSkillId: 'S-12',
  // 本物の解決パネルで描くので、スキル名と威力の幅も本番の記録と同じ項目で持たせる。
  attackerSkillNameHint: '烈風の一閃', defenderSkillNameHint: '鉄壁の構え',
  rolls: { power_a: 9, power_b: 4, base_damage: 9, min_damage_a: 5, max_damage_a: 12, min_damage_b: 2, max_damage_b: 8 },
  damageEvents: [], selfDestructed: [],
  applied: { damage: [], fired_effects: [], statuses: [] }, ...overrides,
});
export const sceneSamples = [
  { id: 'many-lines', label: '付与 → 4効果のまとまり · 連続流し', level: 'normal', state,
    step: step({ applied: {
      damage: [{ target_id: 'd', hp: 9, hp_after: 21, source: 'dice' },
        { target_id: 'd', hp: 6, hp_after: 15, source: 'rupture' },
        { target_id: 'd', hp: 2, hp_after: 13, source: 'fissure' }], statuses: [{target_id:'d',name:'破裂',delta:3},{target_id:'d',name:'出血',delta:2}],
      fired_effects: [
        { term_id: 'W-07', name: '戦慄殺到', results: [{ name: '戦慄', delta: -5 }, { name: 'MP', delta: -5 }] },
        { term_id: 'W-03', name: '破裂爆発', results: [{ name: '破裂', delta: -3 }] },
        { term_id: 'W-05', name: '亀裂崩壊', results: [{ name: '亀裂', delta: -1 }] },
        { term_id: 'W-58', name: '再使用', results: [] },
      ].map(effect => ({ ...effect, actor_id: 'a', target_id: 'd' })),
    } }) },
  { id: 'fear-ko', label: '打ち合い · 戦慄殺到 → 混乱 → 戦闘不能', level: 'normal', state,
    step: step({ applied: {
      damage: [{ target_id: 'd', hp: 9, hp_after: 0, source: 'dice' }],
      fired_effects: [{ term_id: 'W-07', name: '戦慄殺到', actor_id: 'a', target_id: 'd', results: [{ name: '戦慄', delta: -5 }, { name: 'MP', delta: -5 }] }],
      statuses: [{ target_id: 'd', name: '混乱', before: 0, after: 1 }],
    } }) },
  { id: 'rupture', label: '一方攻撃 · 破裂爆発 → 追加ダメージ', level: 'normal', state,
    step: step({ kind: 'one_sided', applied: {
      damage: [{ target_id: 'd', hp: 9, hp_after: 21, source: 'dice' }, { target_id: 'd', hp: 6, hp_after: 15, source: 'rupture' }],
      fired_effects: [{ term_id: 'W-03', name: '破裂爆発', actor_id: 'a', target_id: 'd', results: [{ name: 'HP', delta: -6 }, { name: '破裂', delta: -3 }] }], statuses: [],
    } }) },
  { id: 'summation', label: '広域-合算 · 3人が被弾、1人が戦闘不能', level: 'normal', state,
    step: step({ kind: 'mass_summation', participants: ['sd', 'se', 'sf'],
      rolls: { delta: 8, attacker_power: 23, defender_sum: 15, min_damage_a: 14, max_damage_a: 28, defender_powers: { sd: 5, se: 4, sf: 6 } },
      damageEvents: ['d', 'e', 'f'].map(target_id => ({ target_id, hp: target_id === 'e' ? 3 : 8, hp_after: target_id === 'e' ? 0 : 12, damage_type: 'mass_summation_delta' })),
    }) },
  { id: 'summation-two-ko', label: '広域-合算 · 2人の戦闘不能を0.3秒ずらす', level: 'normal', state,
    step: step({ kind: 'mass_summation', participants: ['sd', 'se', 'sf'],
      rolls: { delta: 8, attacker_power: 23, defender_sum: 15, min_damage_a: 14, max_damage_a: 28, defender_powers: { sd: 5, se: 4, sf: 6 } },
      damageEvents: ['d', 'e', 'f'].map(target_id => ({ target_id, hp: target_id === 'e' ? 3 : 8,
        hp_after: target_id === 'f' ? 12 : 0, damage_type: 'mass_summation_delta' })),
    }) },
  { id: 'eight-effects', label: '8効果のまとまり · 連続移動と減速 · 3人KO', level: 'normal', state,
    step: step({ kind: 'mass_summation', participants: ['sd', 'se', 'sf'],
      rolls: { delta: 8, attacker_power: 23, defender_sum: 15, min_damage_a: 14, max_damage_a: 28, defender_powers: { sd: 5, se: 4, sf: 6 } },
      damageEvents: ['d', 'e', 'f'].map(target_id => ({ target_id, hp: target_id === 'e' ? 3 : 8, hp_after: 0, damage_type: 'mass_summation_delta' })),
      applied: { damage: [], statuses: [], fired_effects: Array.from({ length: 8 }, (_, i) => ({
        ...[
          { term_id: 'W-07', name: '戦慄殺到', results: [{ name: '戦慄', delta: -5 }, { name: 'MP', delta: -5 }] },
          { term_id: 'W-03', name: '破裂爆発', results: [{ name: '破裂', delta: -3 }] },
          { term_id: 'W-05', name: '亀裂崩壊', results: [{ name: '亀裂', delta: -1 }] },
          { term_id: 'W-58', name: '再使用', results: [] },
        ][i % 4], actor_id: 'a', target_id: ['d', 'e', 'f'][i % 3],
      })) },
    }) },
  { id: 'self-destruct', label: '自滅 · 攻撃者の戦闘不能', level: 'normal', state,
    step: step({ kind: 'one_sided', rolls: { base_damage: 2, min_damage_a: 1, max_damage_a: 6 }, selfDestructed: ['a'],
      applied: { damage: [{ target_id: 'd', hp: 2, hp_after: 28, source: 'dice' }], fired_effects: [], statuses: [] },
    }) },
];
