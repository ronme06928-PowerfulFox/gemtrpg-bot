// 計画53§6。状態異常・追加効果・KOのない基本の一太刀どうし。
export const sample = {
  state: {
    phase: 'resolve', characters: [
      { id: 'a', name: '味方', type: 'ally', image: 'images/ally-adventurer.png', hp: 100, mp: 10, fp: 0 },
      { id: 'd', name: '敵', type: 'enemy', image: 'images/wolf-shularker.png', hp: 30, mp: 6, fp: 0 }
    ],
    slots: { sa: { actor_id: 'a' }, sd: { actor_id: 'd' } },
    resolvePresentation: { controller_username: 'GM' }
  },
  step: {
    kind: 'clash', outcome: 'attacker_win', stepIndex: 0, timestamp: 1,
    attackerActorId: 'a', defenderActorId: 'd', attackerSlotId: 'sa', defenderSlotId: 'sd',
    attackerSkillId: 'Ps-00', defenderSkillId: 'Ps-00',
    rolls: { power_a: 9, power_b: 6, base_damage: 9, min_damage_a: 6, max_damage_a: 9, min_damage_b: 6, max_damage_b: 8 },
    damageEvents: [], selfDestructed: [],
    stacks: { a: { before: [], after: [] }, d: { before: [], after: [] } },
    applied: { damage: [{ target_id: 'd', hp: 9, hp_after: 21, source: 'dice' }],
      statuses: [{ target_id: 'a', name: 'FP', before: 0, after: 1, delta: 1, source: 'match_win_fp' }], fired_effects: [] }
  },
  after: { allyFp: 1, enemyHp: 21 }
};
