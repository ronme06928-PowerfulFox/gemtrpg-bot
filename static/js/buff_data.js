/**
 * バフ・デバフ・状態異常の定義データ
 */
window.BUFF_DATA = {
    // 静的定義 (説明文などを固定したい場合)
    STATIC_DATA: {
        "混乱": {
            name: "混乱",
            description: "MPが尽き、意識が朦朧としている。受けるダメージ1.5倍、まともな行動ができない。",
            type: "debuff"
        },
        "行動不能": {
            name: "行動不能",
            description: "次のラウンド、行動できない。",
            type: "debuff"
        },
        "再回避ロック": {
            name: "再回避",
            description: "このラウンド中、特定のスキルでしか回避できない。",
            type: "debuff"
        },
        "挑発中": {
            name: "挑発",
            description: "次のラウンド、攻撃対象を自分に固定する。",
            type: "debuff"
        },
        "破裂威力減少無効": {
            name: "破裂威力減少無効",
            description: "このラウンドでこのキャラに誘発する破裂爆発は、破裂の値を消費しない。",
            type: "buff"
        }
    },

    // 動的パターン定義
    DYNAMIC_PATTERNS: [
        {
            // パターン: [名前]_Atk[数値]
            regex: /^(.*)_Atk(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `このラウンド中、攻撃威力+${matches[2]}。`,
                    type: "buff"
                };
            }
        },
        {
            // パターン: [名前]_AtkDown[数値]
            regex: /^(.*)_AtkDown(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `このラウンド中、攻撃威力-${matches[2]}。`,
                    type: "debuff"
                };
            }
        },
        {
            // パターン: [名前]_Def[数値]
            regex: /^(.*)_Def(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `このラウンド中、守備威力+${matches[2]}。`,
                    type: "buff"
                };
            }
        },
        {
            // パターン: [名前]_DefDown[数値]
            regex: /^(.*)_DefDown(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `このラウンド中、守備威力-${matches[2]}。`,
                    type: "debuff"
                };
            }
        },
        {
            // パターン: [名前]_Phys[数値]
            regex: /^(.*)_Phys(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `このラウンド中、物理補正+${matches[2]}。`,
                    type: "buff"
                };
            }
        },
        {
            // パターン: [名前]_PhysDown[数値]
            regex: /^(.*)_PhysDown(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `このラウンド中、物理補正-${matches[2]}。`,
                    type: "debuff"
                };
            }
        },
        {
            // パターン: [名前]_Mag[数値]
            regex: /^(.*)_Mag(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `このラウンド中、魔法補正+${matches[2]}。`,
                    type: "buff"
                };
            }
        },
        {
            // パターン: [名前]_MagDown[数値]
            regex: /^(.*)_MagDown(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `このラウンド中、魔法補正-${matches[2]}。`,
                    type: "debuff"
                };
            }
        },
        {
            // パターン: [名前]_Crack[数値] (持続型)
            regex: /^(.*)_Crack(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `このラウンド中、自分が付与する亀裂の値+${matches[2]}。`,
                    type: "buff"
                };
            }
        },
        {
            // パターン: [名前]_CrackOnce[数値] (消費型)
            regex: /^(.*)_CrackOnce(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `次に亀裂を付与する際、その値+${matches[2]}。適用後に消滅する。`,
                    type: "buff"
                };
            }
        },
        {
            // パターン: [名前]_DaIn[数値]
            regex: /^(.*)_DaIn(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `受けるダメージが ${matches[2]}% 増加する。`,
                    type: "debuff"
                };
            }
        },
        {
            // パターン: [名前]_DaCut[数値]
            regex: /^(.*)_DaCut(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `受けるダメージを ${matches[2]}% 軽減する。`,
                    type: "buff"
                };
            }
        },
        {
            // パターン: [名前]_BleedReact[数値]
            regex: /^(.*)_BleedReact(\d+)$/,
            generator: function (matches) {
                return {
                    name: matches[1],
                    description: `ダメージを受けた時、自分の出血+${matches[2]}。`,
                    type: "debuff"
                };
            }
        }
    ],

    /**
     * バフ名から定義データを検索して返す
     * @param {string} buffId
     */
    get: function (buffId) {
        // 1. 静的定義チェック
        if (this.STATIC_DATA[buffId]) return this.STATIC_DATA[buffId];

        // 2. パターンマッチチェック
        for (const pattern of this.DYNAMIC_PATTERNS) {
            const match = buffId.match(pattern.regex);
            if (match) {
                return pattern.generator(match);
            }
        }

        // 3. フォールバック
        return { name: buffId, description: "効果不明", type: "unknown" };
    }
};