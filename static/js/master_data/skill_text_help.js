(function () {
    const COND_OP_MEANINGS = {
      GTE: "以上（>=）",
      LTE: "以下（<=）",
      GT: "より大きい（>）",
      LT: "より小さい（<）",
      EQUALS: "等しい（==）",
      CONTAINS: "含む（文字列は部分一致、配列は要素一致）"
    };
    const COND_SOURCE_MEANINGS = {
      self: "自分（actor）の状態値を参照します。例: HP / MP / FP / 速度値。",
      target: "対象（target）の状態値を参照します。例: targetの破裂や出血。",
      skill: "発動者側スキル（actor_skill）の情報を参照します。主に param=tags + CONTAINS。",
      target_skill: "対象側スキル（target_skill）の情報を参照します。主に相手スキルの tags 判定に使います。対抗相手のスキル情報が無い場面では条件は false になります。",
      relation: "actor と target の陣営関係を 0/1 で参照します。param は same_team / target_is_ally / target_is_enemy を使います。",
      battle: "バトルの状態（ラウンド数など）を参照します。param=round でその時点のラウンド数を取得できます。"
    };
    const COND_SOURCE_PARAM_HINTS = {
      self: "推奨param: name / baseName / tag_ids / HP / MP / FP / 速度値 / 各種状態名 / 凝魔_count / 蓄力_count / buff_count:凝魔 / 状態異常スタック合計:出血,破裂,亀裂,戦慄,荊棘（列挙必須）",
      target: "推奨param: name / baseName / tag_ids / HP / MP / FP / 速度値 / 破裂 / 出血 / 亀裂 / 凝魔_count / 蓄力_count / 状態異常スタック合計:出血,破裂,亀裂（列挙必須）",
      skill: "推奨param: tags（operator=CONTAINS 推奨）",
      target_skill: "推奨param: tags（operator=CONTAINS 推奨）",
      relation: "推奨param: same_team / target_is_ally / target_is_enemy（EQUALS 0/1）",
      battle: "推奨param: round（現在ラウンド数。例: operator=GTE, value=3 → 3ラウンド以降に発動）"
    };
    const TIMING_MEANINGS = {
      PRE_MATCH: "判定前の事前処理。威力補正・付与準備向け。",
      BEFORE_POWER_ROLL: "威力ロール直前。対抗結果に関わる補正向け。",
      WIN: "マッチ勝利時のみ発動。",
      LOSE: "マッチ敗北時のみ発動。",
      HIT: "命中成立時に発動。",
      UNOPPOSED: "一方攻撃時（無対抗）に発動。",
      AFTER_DAMAGE_APPLY: "ダメージ適用後に発動。",
      RESOLVE_START: "Resolve開始時に発動。",
      RESOLVE_STEP_END: "Resolveの各ステップ終了時に発動。",
      RESOLVE_END: "Resolve終了時に発動。",
      END_MATCH: "マッチ処理完了後に発動。",
      END_ROUND: "ラウンド終了時に発動。",
      IMMEDIATE: "即時発動（割り込み系）。",
      BATTLE_START: "戦闘開始時に発動。"
    };
    const HELP_ROWS = [["schema","現行は skill_json_rule_v2 固定で必須"],["id","任意だが推奨。未入力でも実行可能"],["target_scope: same_team","同陣営単体を対象にする"],["tag: ally_target","同陣営単体タグ（互換）"],["tag: no_damage","非ダメージ扱い"],["timing: PRE_MATCH","マッチ前処理"],["timing: HIT/WIN/LOSE","的中時/勝利時/敗北時"],["condition.source: target_skill","対象側が宣言したスキル情報（主に tags）を参照。相手スキル情報が無い場面では条件false"],["condition.source: relation","actor-targetの関係を参照。paramは same_team / target_is_ally / target_is_enemy（0/1判定）"],["condition.param: 蓄力_count","対象の特殊バフcountを参照"],["condition.param: buff_count:凝魔","buff_count接頭辞でも特殊バフcountを参照"],["type: APPLY_BUFF","現行は buff_id 指定で付与"],["type: REMOVE_BUFF","現行は buff_id 指定で解除"],["APPLY_BUFF(Bu-11/Bu-12)","加速/減速は lasting=1, delay=1（次ラウンド有効）を推奨"],["APPLY_BUFF.count","スタック系バフの付与回数（凝魔/蓄力など）"],["type: CONSUME_BUFF_COUNT_FOR_GAIN","指定スタックを消費し、FP/MP/HPやバフ付与を行う"],["type: CONSUME_BUFF_COUNT_FOR_POWER","指定スタックを消費し、基礎/最終威力を増減"],["state_receive_bonus","受け手側の状態付与補正（例: 震盪で受ける破裂付与量+N）"],["type: SUMMON_CHARACTER","summon_template_idを使って召喚"],["power_bonus: FIXED","固定加算（value）"],["power_bonus: FIXED_IF_EXISTS","paramが閾値以上で固定加算"],["power_bonus: PER_N_BONUS","Nごとに加算"],["power_bonus: MULTIPLY","param × value_per_param"],["buff_name: *_AtkN / *_DaInN","旧式の動的バフ命名（新規は非推奨）"]];
    HELP_ROWS.push(["condition.param: 状態異常スタック合計:出血,破裂,...","状態異常スタック合算。省略形（状態名なし）は不可。"]);
    HELP_ROWS.push(["condition.source: battle, param: round","現在のラウンド数を参照。例: source=battle, param=round, operator=GTE, value=3 → 3ラウンド以降のみ発動"]);
    HELP_ROWS.push(["condition.param: name / baseName / tag_ids","名前はEQUALS/CONTAINS、tag_idsはCONTAINSで要素完全一致。disabled_tag_idsは判定から除外"]);
    HELP_ROWS.push(["CUSTOM_EFFECT: DEAL_TARGET_MAX_HP_DAMAGE","対象へmaxHpと同値の倍率・軽減を無視するダメージ。例: 対象の特徴に「瓦礫」があるなら、その最大HPと同じ値のダメージを与える"]);
    HELP_ROWS.push(["type: SCHEDULE_EFFECT","RESOLVE_STARTでeffectを予約し、round_offset後のラウンド開始時に実行。effect/repeat_countはextra_jsonへ指定"]);
    HELP_ROWS.push(["type: APPLY_BUFF_FROM_CHARACTER_COUNT","character_filterに一致するフィールド上の人数×value_per_characterを最終威力バフへ変換"]);
    HELP_ROWS.push(["effects[].repeat_count","同じエフェクトをN回繰り返す（省略=1）。例: repeat_count=3 で出血+2を3回 → 合計+6相当。ランダム抽選がある場合は毎回抽選される"]);
    HELP_ROWS.push(["target.type: random_single（インテント）","バトルインテントレベルの設定。スキルJSON外（NPC行動定義等）でランダムターゲット指定。random_target_scope: enemy/ally/any"]);
    HELP_ROWS.push(["effects[].target_select: RANDOM","エフェクトレベルのランダム対象選択（既存機能）。target_filter: ENEMY/ALLY/ALL, target_count: N"]);
    const PB_RULE_SPEC = {
      FIXED: {
        required: ["value"],
        optional: ["apply_to", "condition", "max_bonus", "min_bonus"],
        unused: ["source", "param", "per_N", "threshold", "value_per_param"]
      },
      FIXED_IF_EXISTS: {
        required: ["source", "param", "value"],
        optional: ["threshold", "apply_to", "condition", "max_bonus", "min_bonus"],
        unused: ["per_N", "value_per_param"]
      },
      PER_N_BONUS: {
        required: ["source", "param", "per_N", "value"],
        optional: ["apply_to", "condition", "max_bonus", "min_bonus"],
        unused: ["threshold", "value_per_param"]
      },
      MULTIPLY: {
        required: ["source", "param", "value_per_param"],
        optional: ["apply_to", "condition", "max_bonus", "min_bonus"],
        unused: ["value", "per_N", "threshold"]
      }
    };
    const EFFECT_TYPE_SPEC = {
      APPLY_STATE: {
        meaning: "target に state_name を value だけ加算/減算します。",
        value_kind: "flat",
        value_help: "実数値。例: +3 / -2",
        required: ["state_name", "value"],
        optional: ["target", "condition", "extra_json(rounds)"],
        unused: ["source", "source_param", "per_N", "buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id"]
      },
      APPLY_STATE_PER_N: {
        meaning: "source.source_param を per_N ごとに区切り、value を段階適用して state_name に加算します。",
        value_kind: "flat",
        value_help: "1段階あたりの実数値。例: per_N=3, value=2",
        required: ["state_name", "source", "source_param", "per_N", "value"],
        optional: ["target", "condition", "extra_json(max_value,rounds)"],
        unused: ["buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id"]
      },
      APPLY_BUFF_PER_N: {
        meaning: "source.source_param を per_N ごとに区切り、value 段階分のスタックを buff_id にまとめて付与します。",
        value_kind: "flat",
        value_help: "1段階あたりの付与スタック数。例: per_N=3, value=1",
        required: ["buff_id", "source", "source_param", "per_N", "value"],
        optional: ["target", "condition", "extra_json(max_count)"],
        unused: ["state_name", "buff_name", "skill_id", "lasting", "delay", "summon_template_id"]
      },
      MULTIPLY_STATE: {
        meaning: "target の state_name に倍率 value を適用します。",
        value_kind: "multiplier",
        value_help: "倍率。1.2=120%, 0.8=80%",
        required: ["state_name", "value"],
        optional: ["target", "condition"],
        unused: ["source", "source_param", "per_N", "buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id"]
      },
      APPLY_BUFF: {
        meaning: "buff_id のバフを付与します。",
        value_kind: "none",
        value_help: "通常未使用。強度は buff 側定義で管理",
        required: ["buff_id"],
        optional: ["lasting", "delay", "target", "condition", "extra_json(data,flavor)"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_name", "skill_id", "summon_template_id", "value"]
      },
      CONSUME_BUFF_COUNT_FOR_GAIN: {
        meaning: "指定したバフスタックを消費できるときだけ、gainsの追加効果を適用します。",
        value_kind: "none",
        value_help: "通常未使用。consume_required / gains は extra_json で指定",
        required: ["buff_name"],
        optional: ["target", "condition", "extra_json(consume_required,gains)"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "skill_id", "lasting", "delay", "summon_template_id", "value"]
      },
      CONSUME_BUFF_COUNT_FOR_POWER: {
        meaning: "指定したバフスタックを消費できるぶんだけ、威力補正を生成します。",
        value_kind: "none",
        value_help: "通常未使用。consume_max / value_per_stack / apply_to / min_consume は extra_json で指定",
        required: ["buff_name"],
        optional: ["target", "condition", "extra_json(consume_max,value_per_stack,apply_to,min_consume)"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "skill_id", "lasting", "delay", "summon_template_id", "value"]
      },
      CONVERT_STACK_RESOURCE_VARIANT: {
        meaning: "凝魔/蓄力などのスタック資源を、スタック数そのままで別variantに変換します。",
        value_kind: "none",
        value_help: "通常未使用。to_variant / require_count_gte は extra_json で指定",
        required: ["buff_name"],
        optional: ["target", "condition", "extra_json(to_variant,require_count_gte)"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "skill_id", "lasting", "delay", "summon_template_id", "value"]
      },
      GRANT_SKILL: {
        meaning: "target に skill_id のスキルを一時付与します。",
        value_kind: "none",
        value_help: "通常未使用。回数/期間は extra_json で指定",
        required: ["skill_id"],
        optional: ["target", "condition", "extra_json(grant_mode,duration,uses,overwrite)"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "buff_name", "lasting", "delay", "summon_template_id", "value"]
      },
      REMOVE_BUFF: {
        meaning: "target から buff_id を持つバフを解除します。",
        value_kind: "none",
        value_help: "通常未使用",
        required: ["buff_id"],
        optional: ["target", "condition"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_name", "skill_id", "lasting", "delay", "summon_template_id", "value"]
      },
      DAMAGE_BONUS: {
        meaning: "与ダメージ計算に value を固定加算します。",
        value_kind: "flat",
        value_help: "実数値。例: +5 / -3",
        required: ["value"],
        optional: ["target", "condition"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id"]
      },
      MODIFY_ROLL: {
        meaning: "判定ロールの結果に value を補正します。",
        value_kind: "flat",
        value_help: "実数値。例: +1 / -1",
        required: ["value"],
        optional: ["target", "condition"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id"]
      },
      USE_SKILL_AGAIN: {
        meaning: "同スキルの再使用を許可します。",
        value_kind: "none",
        value_help: "通常未使用。回数制御や再使用コストは extra_json",
        required: [],
        optional: ["target", "condition", "extra_json(max_reuses,consume_cost,reuse_cost,stack_reuse_cost)"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id", "value"]
      },
      CUSTOM_EFFECT: {
        meaning: "独自処理を呼び出します。詳細は value/extra_json を実装側仕様に合わせます。",
        value_kind: "custom",
        value_help: "実装依存。固定値/倍率どちらもあり得る",
        required: ["value"],
        optional: ["target", "condition", "extra_json(data)"],
        unused: ["source", "source_param", "per_N", "buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id"]
      },
      MODIFY_BASE_POWER: {
        meaning: "基礎威力に value を加算/減算します。",
        value_kind: "flat",
        value_help: "実数値。例: +2 / -2",
        required: ["value"],
        optional: ["target", "condition"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id"]
      },
      MODIFY_FINAL_POWER: {
        meaning: "最終威力に value を加算/減算します。",
        value_kind: "flat",
        value_help: "実数値。例: +4 / -4",
        required: ["value"],
        optional: ["target", "condition"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id"]
      },
      DRAIN_HP: {
        meaning: "target から HP を吸収します。",
        value_kind: "flat",
        value_help: "実数値。例: 10",
        required: ["value"],
        optional: ["target", "condition"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id"]
      },
      SUMMON_CHARACTER: {
        meaning: "summon_template_id に対応するユニットを召喚します。",
        value_kind: "none",
        value_help: "通常未使用。期間は extra_json で指定",
        required: ["summon_template_id"],
        optional: ["target", "condition", "extra_json(summon_duration_mode,summon_duration)"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "buff_name", "skill_id", "lasting", "delay", "value"]
      },
      SCHEDULE_EFFECT: {
        meaning: "nested effectを指定ラウンド後のラウンド開始時に予約実行します。",
        value_kind: "none",
        value_help: "通常未使用。effect / round_offset / repeat_countはextra_jsonで指定",
        required: [],
        optional: ["target", "extra_json(effect,round_offset,repeat_count,schedule_key)"],
        unused: ["source", "source_param", "per_N", "state_name", "buff_id", "buff_name", "skill_id", "lasting", "delay", "summon_template_id", "value"]
      },
      APPLY_BUFF_FROM_CHARACTER_COUNT: {
        meaning: "character_filterに一致する人数から可変値の最終威力バフを生成します。",
        value_kind: "none",
        value_help: "通常未使用。character_filter / value_per_characterはextra_jsonで指定",
        required: ["buff_name"],
        optional: ["target", "buff_id", "lasting", "delay", "extra_json(character_filter,value_per_character,apply_to)"],
        unused: ["source", "source_param", "per_N", "state_name", "skill_id", "summon_template_id", "value"]
      }
    };

  const h=window.CatalogGlossary.escape;
  const table=(head,rows)=>`<div class="cat-text-help-table"><table><thead><tr>${head.map(value=>`<th>${h(value)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(value=>`<td>${h(Array.isArray(value)?value.join('、'):value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const section=(title,body)=>`<details><summary>${h(title)}</summary>${body}</details>`;
  function render(refs={}) {
    return `<details class="cat-text-help"><summary>書ける言い回し・項目の早見表</summary><p class="cat-caption">決まった言い回しだけを読み取ります。区切りは「。」と改行です。読めない行は欄名・原文・理由を表示します。</p>`
      +section('文章の例',table(['欄','例'],[['コスト','（使用時）FPを2消費。'],['発動時効果','（的中時）3ラウンドの亀裂1を付与。'],['特記','対象に亀裂があるなら基礎威力+1。']]))
      +section('項目',table(['key','意味'],HELP_ROWS))
      +section('timing · タイミング',table(['値','意味'],Object.entries(TIMING_MEANINGS)))
      +section('condition · 条件',table(['source','意味','param'],Object.entries(COND_SOURCE_MEANINGS).map(([key,value])=>[key,value,COND_SOURCE_PARAM_HINTS[key]]))+table(['operator','意味'],Object.entries(COND_OP_MEANINGS)))
      +section('power_bonus · 威力補正',table(['operation','必須','任意','未使用'],Object.entries(PB_RULE_SPEC).map(([key,row])=>[key,row.required,row.optional,row.unused])))
      +section('effects · 効果',table(['type','意味','value','必須','任意','未使用'],Object.entries(EFFECT_TYPE_SPEC).map(([key,row])=>[key,row.meaning,row.value_help,[...row.required,...(row.requiredAny || []).map(keys=>keys.join(' / '))],row.optional,row.unused])))
      +section('公開中のバフ・召喚名',table(['ID','名前'],[...(refs.buff_refs || []),...(refs.summon_refs || [])].map(row=>[row.id,row.name])))+'</details>';
  }
  window.CatalogSkillTextHelp={powerRules:PB_RULE_SPEC,render};
})();
