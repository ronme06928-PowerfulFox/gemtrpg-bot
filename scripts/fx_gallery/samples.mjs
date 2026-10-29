// 正規化済みtraceはPR4のテストと同じ形。見本の値はこのファイルに集約する。
const sample = (id, effect, label, params = {}, anchor = '.side.defender .name') =>
  ({ id, effect, label, params, anchor, level: 'normal' });

export const effectSamples = [
  sample('float-damage', 'float-text', 'HP −9', { text: '−9', tone: 'damage' }),
  sample('float-heal', 'float-text', 'HP +12', { text: '+12', tone: 'heal' }),
  sample('round', 'round-banner', 'ROUND 3', { text: 'ROUND 3' }, '.resolve-flow-card'),
  sample('power', 'power-roll', '威力 12', { text: '12' }, '.actual.attacker'),
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
  ...['enemy', 'ally', 'self'].map(tone => sample(`effect-${tone}`, 'effect-name', `戦慄殺到 / ${tone}`, {
    text: '戦慄殺到', tone, self: tone === 'self', results: [{ name: '戦慄', delta: -5 }, { name: 'MP', delta: -5 }, { name: '混乱', delta: null }],
  })),
  sample('confusion', 'effect-name', '混乱（結果なし）', { text: '混乱', tone: 'ally', results: [] }),
  sample('ko-hit', 'ko-shatter', '戦闘不能', { mode: 'hit' }, '.resolve-flow-background.defender'),
  sample('ko-chip', 'ko-shatter', '参加者の戦闘不能', { mode: 'chip' }, '.participant-chip[data-actor-id="e"] .resolve-flow-portrait-inline'),
  sample('chat', 'chat-dice', '2d6+5 → 13', {
    text: '13', images: Array.from({ length: 6 }, (_, i) => `/static/images/dice/die-${i + 1}.svg`),
  }, '.chat-total'),
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
  attackerSlotId: 'sa', defenderSlotId: 'sd', attackerSkillId: 'A', defenderSkillId: 'D',
  rolls: { power_a: 9, power_b: 4, base_damage: 9 },
  damageEvents: [], selfDestructed: [],
  applied: { damage: [], fired_effects: [], statuses: [] }, ...overrides,
});
export const sceneSamples = [
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
      rolls: { delta: 8, attacker_power: 23, defender_powers: { sd: 5, se: 4, sf: 6 } },
      damageEvents: ['d', 'e', 'f'].map(target_id => ({ target_id, hp: target_id === 'e' ? 3 : 8, hp_after: target_id === 'e' ? 0 : 12, damage_type: 'mass_summation_delta' })),
    }) },
  { id: 'self-destruct', label: '自滅 · 攻撃者の戦闘不能', level: 'normal', state,
    step: step({ kind: 'one_sided', rolls: { base_damage: 2 }, selfDestructed: ['a'],
      applied: { damage: [{ target_id: 'd', hp: 2, hp_after: 28, source: 'dice' }], fired_effects: [], statuses: [] },
    }) },
];
