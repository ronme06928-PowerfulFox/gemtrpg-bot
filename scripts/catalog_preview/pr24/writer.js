// PR60-24 の試作：スキルの効果の設定から、ゲームの書き方の文章（コスト・発動時効果・特記）を作る（本番には入らない）。
// 言い回しは「文章から効果を作る」の読み取り（skill_text.js）が読める形に合わせる。文にできない効果は unknown に入れ、文章には入れない。
(function () {
  const TIMINGS = {
    PRE_MATCH: ['W-19', '使用時'], HIT: ['W-20', '的中時'], WIN: ['W-21', 'マッチ勝利時'], LOSE: ['W-22', 'マッチ敗北時'],
    END_ROUND: ['W-26', 'ラウンド終了時'], END_MATCH: ['W-24', 'マッチ終了時'], RESOLVE_START: ['W-27', '戦闘開始時'], UNOPPOSED: ['W-23', '一方攻撃時'],
  };
  const STATES = ['出血', '破裂', '亀裂', '戦慄', '荊棘'];
  const RESOURCES = ['FP', 'MP', 'HP'];
  const PLACES = { base: '基礎威力', dice: 'ダイス威力', final: '最終威力' };
  const OPS = { GTE: '以上', LTE: '以下', LT: '未満', GT: 'より高い' };

  function create(references = {}) {
    const glossary = new Map((references.glossary_refs || []).map(row => [row.display_name || row.name, row.id || row.term_id]));
    const buffs = new Map((references.buff_refs || []).map(row => [row.id, row.name]));
    const link = name => glossary.has(name) ? `[[${glossary.get(name)}|${name}]]` : name;
    const who = source => source === 'self' ? '自分' : '対象';
    const param = value => String(value || '').replace(/_count$/, '');
    const signed = value => (value < 0 ? `${value}` : `+${value}`);
    const buffName = row => buffs.get(row.buff_id) || row.buff_name || row.buff_id;
    const count = row => row.count ?? row.data?.count;

    function condition(cond) {
      if (!cond) return '';
      const name = param(cond.param);
      if (cond.operator === 'EQUALS' && Number(cond.value) === 0) return `${who(cond.source)}に${link(name)}がないなら、`;
      if (cond.operator === 'GTE' && Number(cond.value) === 1 && STATES.includes(name)) return `${who(cond.source)}に${link(name)}があるなら、`;
      const op = OPS[cond.operator];
      return op ? `${who(cond.source)}の${link(name)}が${cond.value}${op}なら、` : null;
    }

    // 効果1つを文（タイミングの印を除いた本文）にする。文にできなければ null。
    function sentence(row) {
      const self = row.target === 'self';
      switch (row.type) {
        case 'APPLY_STATE': {
          const name = row.state_name, value = Number(row.value);
          if (STATES.includes(name)) {
            if (value <= 0) return null;
            const rounds = row.rounds ? `${row.rounds}${link('ラウンド')}の` : '';
            return `${self ? '自分に' : ''}${rounds}${link(name)}${value}を付与`;
          }
          if (RESOURCES.includes(name)) {
            if (self && value > 0) return name === 'FP' ? `FPを${value}得る` : `${name}を${value}回復する`;
            if (self && name === 'HP' && value < 0) return `自身に${-value}ダメージ`;
            if (!self && value < 0) return `相手の${name}を${-value}減少させる`;
          }
          return null;
        }
        case 'APPLY_BUFF': {
          const name = buffName(row), n = count(row), value = row.data?.value;
          const correction = { 'Bu-36': ['物理補正', 1], 'Bu-37': ['物理補正', -1], 'Bu-38': ['魔法補正', 1], 'Bu-39': ['魔法補正', -1] }[row.buff_id];
          if (correction && value !== undefined) {
            const when = row.delay === 1 && row.lasting === 1 ? `次の${link('ラウンド')}で` : row.delay > 1 && row.lasting === 1 ? `${row.delay}${link('ラウンド')}後に` : !row.delay && row.lasting > 1 ? `${row.lasting - 1}${link('ラウンド')}後まで、` : null;
            return when === null ? null : `${when}${self ? '自分' : '対象'}の${link(correction[0])}${signed(correction[1] * value)}`;
          }
          if (['Bu-32', 'Bu-33'].includes(row.buff_id) && self && !row.delay && row.lasting === 1) return `このラウンドで、自分の使用する${row.buff_id === 'Bu-32' ? '攻撃' : '守備'}スキルの${link('最終威力')}+${value}`;
          if (row.buff_id === 'Bu-40' && self) return `このラウンドで自分が付与する${link('亀裂')}の値に+${value}`;
          if (row.buff_id === 'Bu-41' && self) return `次にこのキャラクターが付与する${link('亀裂')}の値+${value}`;
          if (row.buff_id === 'Bu-43') return `${row.delay === 1 && row.lasting === 1 ? `次の${link('ラウンド')}で、` : ''}${self ? '自分' : '対象'}が受けるダメージを${value}%上げる`;
          if (['蓄力', '凝魔'].includes(name) && self) return `${link(name)}${n ?? 1}を得る`;
          if (name === '出血遷延') return `${self ? '自分' : '対象'}に${n ?? row.lasting}${link('ラウンド')}の${link(name)}を付与`;
          if (row.delay === 1 && row.lasting === 1) return `${self ? '自分' : '対象'}に次の${link('ラウンド')}で${link(name)}${n ?? ''}を付与`;
          if (n && row.lasting > 1) return `${n}スタックの${link(name)}を付与。${row.lasting}${link('ラウンド')}継続`;
          return null;
        }
        case 'DAMAGE_BONUS': return `対象に${row.value}ダメージ`;
        case 'CUSTOM_EFFECT': {
          if (row.value === '亀裂崩壊_DAMAGE') return `${link('亀裂崩壊')}。消費した${link('亀裂')}1につき${row.damage_per_fissure ?? 3}ダメージ`;
          if (['破裂爆発', '出血氾濫', '戦慄殺到', '荊棘飛散'].includes(row.value) && !row.rupture_remainder_ratio) return `${self ? '自分に' : ''}${link(row.value)}`;
          return null;
        }
        case 'USE_SKILL_AGAIN': {
          const stack = row.stack_reuse_cost ? `自分の${link(row.stack_reuse_cost.buff_name)}${row.stack_reuse_cost.value}を消費し、` : '';
          const cost = stack + (row.reuse_cost || []).map(item => `${item.type}を${item.value}消費し、`).join('');
          const max = row.max_reuses ?? 1;
          // 上限は1回の使用（スロット）ごとに数える。「1ラウンドに1度まで」とは書かない（2026-11-14 ユーザー決定）。
          const limit = `(この効果による再使用は${max}回まで)`;
          const lack = row.stack_reuse_cost ? `。${row.stack_reuse_cost.buff_name}が不足している場合、この効果は発生しない` : '';
          return `${cost}このスキルを${link('再使用')}。${limit}${lack}`;
        }
        case 'CONSUME_BUFF_COUNT_FOR_GAIN': {
          const gains = row.gains || [];
          if (gains.length !== 1) return null;
          const [gain] = gains;
          if (RESOURCES.includes(gain.type)) return `${link(row.buff_name)}を${row.consume_required}消費し、${gain.type}を${gain.value}${gain.type === 'FP' ? '得る' : '回復する'}`;
          const inner = sentence({ timing: row.timing, ...gain });
          return inner === null ? null : `自分の${link(row.buff_name)}${row.consume_required}を消費し、${inner}。${row.buff_name}が不足している場合、この効果は発生しない`;
        }
        case 'CONSUME_BUFF_COUNT_FOR_POWER':
          return `自分の${link(row.buff_name)}を可能な限り消費し(最大で${row.consume_max})、消費した値だけこのスキルの${link(PLACES[row.apply_to] || '基礎威力')}を上昇させる`;
        case 'APPLY_STATE_PER_N': {
          const max = row.max_value ? `。(最大で${row.max_value})` : '';
          if (row.source === 'self' && row.rounds) return `自分の${link(row.source_param)}${row.per_N}につき${row.value}の${row.rounds}${link('ラウンド')}継続する${link(row.state_name)}を付与${max}`;
          if (row.source === 'target') return `対象の${link(row.source_param)}${row.per_N}につき${link(row.state_name)}${row.value}を付与${max}`;
          return null;
        }
        case 'MULTIPLY_STATE': return `対象の${link(row.state_name)}${link('威力')}を${row.value}倍にする`;
        default: return null;
      }
    }

    function bonusSentence(rule) {
      const op = String(rule.operation || rule.operator || 'FIXED').toUpperCase();
      const place = link(PLACES[rule.apply_to || 'base']);
      const value = Number(rule.value);
      const limit = rule.max_bonus !== undefined ? `(最大で${rule.max_bonus})` : rule.min_bonus !== undefined ? `(最大で${Math.abs(rule.min_bonus)})` : '';
      if (op === 'PER_N_BONUS') return `${who(rule.source)}の${link(param(rule.param))}${rule.per_N}につき、このスキルの${place}${signed(value)}${limit}`;
      if (op === 'FIXED_IF_EXISTS') {
        const threshold = rule.threshold ?? 1;
        return threshold === 1 ? `${who(rule.source)}に${link(param(rule.param))}があるなら${place}${signed(value)}` : `${who(rule.source)}の${link(param(rule.param))}が${threshold}以上なら、このスキルの${place}${signed(value)}`;
      }
      if (op === 'FIXED' && rule.condition) {
        const cond = condition(rule.condition);
        return cond === null ? null : `${cond}このスキルの${place}${signed(value)}`;
      }
      if (op === 'MULTIPLY') return `${who(rule.source)}の${link(param(rule.param))}${link('威力')}の値だけ${place}を加算${limit}`;
      return null;
    }

    function write(payload = {}) {
      const rule = payload.特記処理 || {};
      const unknown = [];
      const cost = (rule.cost || []).map(item => `${item.type}を${item.value}消費`).join('。');
      const groups = [];
      for (const row of rule.effects || []) {
        const body = sentence(row), cond = condition(row.condition);
        if (body === null || cond === null || !TIMINGS[row.timing]) { unknown.push(row); continue; }
        let group = groups.find(item => item.timing === row.timing);
        if (!group) groups.push(group = { timing: row.timing, lines: [] });
        group.lines.push(cond + body);
      }
      const trigger = groups.map(({ timing, lines }) => `([[${TIMINGS[timing][0]}|${TIMINGS[timing][1]}]]):${lines.join('。')}。`).join('');
      const notes = [];
      // 補正を付けない印は、効果ではなく文で持つので、今の特記から引き継ぐ。
      const keep = String(payload.特記 || '').match(/このスキルには(?:物理|魔法)補正を適用しない。?/);
      if (keep) notes.push(keep[0].replace(/。$/, ''));
      for (const bonus of rule.power_bonus || []) {
        const text = bonusSentence(bonus);
        if (text === null) unknown.push(bonus); else notes.push(text);
      }
      return {
        コスト: cost ? `([[W-19|使用時]]):${cost}。` : '',
        発動時効果: trigger,
        特記: notes.length ? `${notes.join('。')}。` : '',
        unknown,
      };
    }
    return { write };
  }
  window.CatalogSkillWriter = { create };
})();
