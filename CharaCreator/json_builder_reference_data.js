window.JSON_BUILDER_REFERENCE = {
  "generated_at": "2026-04-05T14:12:29.228Z",
  "buff_refs": [
    {
      "id": "Bu-00",
      "name": "鋭敏",
      "description": "1ラウンドの間スキルの基礎威力を+1する。",
      "effect": {
        "type": "stat_mod",
        "stat": "基礎威力",
        "value": 1
      },
      "default_duration": 1
    },
    {
      "id": "Bu-01",
      "name": "挑発",
      "description": "このラウンドで全ての相手の攻撃対象を自分に固定する。",
      "effect": {
        "type": "plugin",
        "name": "provoke",
        "category": "debuff"
      },
      "default_duration": 1
    },
    {
      "id": "Bu-02",
      "name": "混乱",
      "description": "受けるダメージが1.5倍になり、行動できない。",
      "effect": {
        "type": "plugin",
        "name": "confusion",
        "category": "debuff",
        "damage_multiplier": 1.5,
        "restore_mp_on_end": false
      },
      "default_duration": 2
    },
    {
      "id": "Bu-03",
      "name": "混乱(戦慄殺到)",
      "description": "受けるダメージが1.5倍になり、行動できない。解除時MP全回復。",
      "effect": {
        "type": "plugin",
        "name": "confusion",
        "category": "debuff",
        "damage_multiplier": 1.5,
        "restore_mp_on_end": true
      },
      "default_duration": 2
    },
    {
      "id": "Bu-04",
      "name": "行動不能",
      "description": "このラウンドの間、行動できなくなる。",
      "effect": {
        "type": "plugin",
        "name": "immobilize",
        "category": "debuff"
      },
      "default_duration": 1
    },
    {
      "id": "Bu-05",
      "name": "再回避ロック",
      "description": "再び回避できるが、特定のスキルしか使用できない。",
      "effect": {
        "type": "plugin",
        "name": "dodge_lock",
        "category": "debuff"
      },
      "default_duration": 1
    },
    {
      "id": "Bu-06",
      "name": "破裂威力減少無効",
      "description": "このキャラに破裂爆発を発動時、破裂の値を消費しない。",
      "effect": {
        "type": "plugin",
        "name": "burst_no_consume",
        "category": "debuff"
      },
      "default_duration": 1
    },
    {
      "id": "Bu-07",
      "name": "時限破裂爆発",
      "description": "一定のラウンド後、このキャラクターに破裂爆発を発動する。",
      "effect": {
        "type": "plugin",
        "name": "timebomb_burst",
        "category": "debuff"
      },
      "default_duration": 1
    },
    {
      "id": "Bu-08",
      "name": "出血遷延",
      "description": "ラウンド終了時などの出血によるダメージ発生時、出血威力が減少しない。",
      "effect": {
        "type": "plugin",
        "name": "bleed_maintenance",
        "category": "debuff"
      },
      "default_duration": 1
    },
    {
      "id": "Bu-09",
      "name": "爆縮",
      "description": "攻撃時、追加で5のダメージを与える。（1回の戦闘で8回まで）",
      "effect": {
        "type": "plugin",
        "name": "implosion",
        "category": "buff"
      },
      "default_duration": -1
    },
    {
      "id": "Bu-10",
      "name": "小麦色の風",
      "description": "ラウンド開始時、50%の確率でFPを1獲得する。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-11",
      "name": "加速",
      "description": "ラウンド開始時、速度補正にスタック数を加算。速度値ロール後にクリアされる。",
      "effect": {
        "type": "plugin",
        "name": "speed_mod",
        "category": "buff"
      },
      "default_duration": -1
    },
    {
      "id": "Bu-12",
      "name": "減速",
      "description": "ラウンド開始時、速度補正にスタック数を減算。速度値ロール後にクリアされる。",
      "effect": {
        "type": "plugin",
        "name": "speed_mod",
        "category": "debuff"
      },
      "default_duration": -1
    },
    {
      "id": "Bu-13",
      "name": "大魔女の末裔",
      "description": "MPの上限+1。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-14",
      "name": "神樹の恩寵",
      "description": "ラウンド終了時、HPを3回復する。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-15",
      "name": "厄災を探究せし理性",
      "description": "魔法スキル限定の経験+1。情報系探索スキルのLvが+1。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-16",
      "name": "厄災と共に生きる知恵",
      "description": "経験+1。情報系探索スキルのLvが-1。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-17",
      "name": "反撃の石",
      "description": "防御スキルを使用してマッチ勝利時、自分スキルの威力が相手スキルの威力を越えた分の値だけ相手に反撃ダメージ。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-18",
      "name": "誉れ高き刃",
      "description": "斬撃スキルの基礎威力+1。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-19",
      "name": "畏怖の衣",
      "description": "マッチ相手のスキル最終威力を-１。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-20",
      "name": "世界を見下ろす黒鳥",
      "description": "他の国の出身ボーナスを一つ選んで取得できる。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-21",
      "name": "色とりどりの輝石",
      "description": "他の国の出身ボーナスを一つ選んで取得できる。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-22",
      "name": "空を巡る叡智",
      "description": "他の国の出身ボーナスを一つ選んで取得できる。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-23",
      "name": "狭霧に息づく神秘",
      "description": "ラウンド終了時、自身のMPを1回復する。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-24",
      "name": "いずれ彩られる純白",
      "description": "攻撃スキル的中時、対象に色彩を付与する。2ラウンド継続。自分と同陣営のキャラクターが色彩を持つ相手陣営キャラクターを対象に攻撃スキルを使用する時、スキルの最終威力+1。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-25",
      "name": "アル・カルメイルの古血",
      "description": "HPの最大値+20。本能と隠密の探索スキルレベル+2。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-26",
      "name": "活力の行き重なる落合",
      "description": "対話と鑑定のスキルレベル+2。戦闘中、回避スキルのダイス威力+1。相手陣営にヴァルヴァイレ出身のキャラクターが存在する時、この効果の効果量+1。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-27",
      "name": "盛夏と共鳴る高揚",
      "description": "五感、本能、運動、回避のスキルレベルを+1する。戦闘中、このラウンドでフィールドに自分と同じ速度のキャラクターがいるなら、自分が使用するスキルの基礎威力+1。",
      "effect": {},
      "default_duration": -1
    },
    {
      "id": "Bu-28",
      "name": "色彩",
      "description": "これを持つキャラクターを対象に攻撃スキルを使用する相手陣営キャラクターの、スキルの最終威力+1。",
      "effect": {},
      "default_duration": 2
    }
  ],
  "skill_refs": [
    {
      "id": "B-01",
      "name": "B-01",
      "tags": [
        "即時発動",
        "宝石の加護スキル"
      ]
    },
    {
      "id": "B-02",
      "name": "B-02",
      "tags": [
        "即時発動",
        "宝石の加護スキル"
      ]
    },
    {
      "id": "B-03",
      "name": "B-03",
      "tags": [
        "即時発動",
        "宝石の加護スキル"
      ]
    },
    {
      "id": "B-04",
      "name": "B-04",
      "tags": [
        "即時発動",
        "宝石の加護スキル"
      ]
    },
    {
      "id": "C-00",
      "name": "C-00",
      "tags": []
    },
    {
      "id": "D-00",
      "name": "D-00",
      "tags": [
        "守備",
        "防御"
      ]
    },
    {
      "id": "D-01",
      "name": "D-01",
      "tags": [
        "守備",
        "回避"
      ]
    },
    {
      "id": "D-02",
      "name": "D-02",
      "tags": [
        "守備",
        "防御"
      ]
    },
    {
      "id": "D-03",
      "name": "D-03",
      "tags": [
        "守備",
        "回避"
      ]
    },
    {
      "id": "D-04",
      "name": "D-04",
      "tags": [
        "守備",
        "回避"
      ]
    },
    {
      "id": "E-00",
      "name": "E-00",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-01",
      "name": "E-01",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-02",
      "name": "E-02",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-03",
      "name": "E-03",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-04",
      "name": "E-04",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-05",
      "name": "E-05",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-06",
      "name": "E-06",
      "tags": [
        "守備",
        "防御"
      ]
    },
    {
      "id": "E-07",
      "name": "E-07",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-08",
      "name": "E-08",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-09",
      "name": "E-09",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-10",
      "name": "E-10",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-11",
      "name": "E-11",
      "tags": [
        "攻撃",
        "広域"
      ]
    },
    {
      "id": "E-12",
      "name": "E-12",
      "tags": [
        "攻撃",
        "広域",
        "マッチ不可",
        "ラウンド終了"
      ]
    },
    {
      "id": "E-13",
      "name": "E-13",
      "tags": [
        "攻撃",
        "広域"
      ]
    },
    {
      "id": "E-14",
      "name": "E-14",
      "tags": [
        "攻撃",
        "広域"
      ]
    },
    {
      "id": "E-15",
      "name": "E-15",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-16",
      "name": "E-16",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-17",
      "name": "E-17",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-18",
      "name": "E-18",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-19",
      "name": "E-19",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-20",
      "name": "E-20",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-21",
      "name": "E-21",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "E-22",
      "name": "E-22",
      "tags": [
        "攻撃",
        "自滅"
      ]
    },
    {
      "id": "E-23",
      "name": "E-23",
      "tags": [
        "攻撃",
        "強硬"
      ]
    },
    {
      "id": "E-24",
      "name": "E-24",
      "tags": [
        "攻撃",
        "牽制"
      ]
    },
    {
      "id": "E-25",
      "name": "E-25",
      "tags": [
        "非ダメージ",
        "同陣営指定"
      ]
    },
    {
      "id": "Mb-00",
      "name": "Mb-00",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mb-01",
      "name": "Mb-01",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mb-02",
      "name": "Mb-02",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mb-03",
      "name": "Mb-03",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mb-04",
      "name": "Mb-04",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mb-05",
      "name": "Mb-05",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mb-06",
      "name": "Mb-06",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mb-07",
      "name": "Mb-07",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mb-08",
      "name": "Mb-08",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mb-09",
      "name": "Mb-09",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mb-10",
      "name": "Mb-10",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-00",
      "name": "Mp-00",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-01",
      "name": "Mp-01",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-02",
      "name": "Mp-02",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-03",
      "name": "Mp-03",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-04",
      "name": "Mp-04",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-05",
      "name": "Mp-05",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-06",
      "name": "Mp-06",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-07",
      "name": "Mp-07",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-08",
      "name": "Mp-08",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-09",
      "name": "Mp-09",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Mp-10",
      "name": "Mp-10",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-00",
      "name": "Ms-00",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-01",
      "name": "Ms-01",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-02",
      "name": "Ms-02",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-03",
      "name": "Ms-03",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-04",
      "name": "Ms-04",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-05",
      "name": "Ms-05",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-06",
      "name": "Ms-06",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-07",
      "name": "Ms-07",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-08",
      "name": "Ms-08",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-09",
      "name": "Ms-09",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ms-10",
      "name": "Ms-10",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-00",
      "name": "Pb-00",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-01",
      "name": "Pb-01",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-02",
      "name": "Pb-02",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-03",
      "name": "Pb-03",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-04",
      "name": "Pb-04",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-05",
      "name": "Pb-05",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-06",
      "name": "Pb-06",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-07",
      "name": "Pb-07",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-08",
      "name": "Pb-08",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-09",
      "name": "Pb-09",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pb-10",
      "name": "Pb-10",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-00",
      "name": "Pp-00",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-01",
      "name": "Pp-01",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-02",
      "name": "Pp-02",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-03",
      "name": "Pp-03",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-04",
      "name": "Pp-04",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-05",
      "name": "Pp-05",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-06",
      "name": "Pp-06",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-07",
      "name": "Pp-07",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-08",
      "name": "Pp-08",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-09",
      "name": "Pp-09",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Pp-10",
      "name": "Pp-10",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-00",
      "name": "Ps-00",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-01",
      "name": "Ps-01",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-02",
      "name": "Ps-02",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-03",
      "name": "Ps-03",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-04",
      "name": "Ps-04",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-05",
      "name": "Ps-05",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-06",
      "name": "Ps-06",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-07",
      "name": "Ps-07",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-08",
      "name": "Ps-08",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-09",
      "name": "Ps-09",
      "tags": [
        "攻撃"
      ]
    },
    {
      "id": "Ps-10",
      "name": "Ps-10",
      "tags": [
        "攻撃"
      ]
    }
  ],
  "summon_refs": [
    {
      "id": "U-00",
      "name": "鉄の小蜘蛛",
      "summon_duration_mode": "duration_rounds",
      "summon_duration": 3
    },
    {
      "id": "U-01",
      "name": "マフィアの下っ端",
      "summon_duration_mode": "permanent",
      "summon_duration": 0
    }
  ],
  "state_refs": [
    "FP",
    "HP",
    "MP",
    "亀裂",
    "荊棘",
    "出血",
    "戦慄",
    "速度値",
    "破裂"
  ]
};
