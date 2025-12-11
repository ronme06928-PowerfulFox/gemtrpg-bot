/**
 * バフ・デバフ・状態異常の定義データ
 * カテゴリごとに分けて管理し、get()メソッドで一括検索可能にする
 */
const BUFF_DATA = {
    // --- 有利な効果 (Buffs) ---
    BUFFS: {
        "攻撃威力+5(1R)": {
            name: "猛攻の輝き",
            description: "このラウンド中、自分の使用する攻撃スキルの威力+5。",
            type: "buff"
        },
        "守備威力+5(1R)": {
            name: "守護の輝き",
            description: "このラウンド中、自分の使用する守備スキルの威力+5。",
            type: "buff"
        },
        "破裂威力減少無効": {
            name: "破裂威力減少無効",
            description: "このラウンドでこのキャラに誘発する破裂爆発は、破裂の値を消費しない。",
            type: "buff"
        },
        "亀裂ラウンドボーナス": {
            name: "亀裂付与ボーナス",
            description: "このラウンドで自分が付与する亀裂の値に+1。",
            type: "buff"
        },
        "魔法補正UP(1R)": {
            name: "魔法補正アップ",
            description: "次のラウンド、魔法補正+1。",
            type: "buff"
        }
    },

    // --- 不利な効果・制限 (Debuffs / Status Ailments) ---
    DEBUFFS: {
        "挑発中": {
            name: "挑発",
            description: "次のラウンド、全ての相手側キャラの攻撃対象を自分に固定する。",
            type: "debuff"
        },
        "再回避ロック": {
            name: "再回避",
            description: "回避に成功したため、行動回数が回復した。このラウンド中、このスキルでしか回避できない。",
            type: "debuff" // 制限行動なのでデバフ扱い
        },
        "行動不能": {
            name: "行動不能",
            description: "次のラウンド、行動できない。",
            type: "debuff"
        },
        "魔法補正DOWN(1R)": {
            name: "魔法補正ダウン",
            description: "次のラウンド、魔法補正-1。",
            type: "debuff"
        },
        "混乱": {
            name: "混乱",
            description: "MPが尽き、意識が朦朧としている。受けるダメージ1.5倍、まともな行動ができない。",
            type: "debuff"
        }
    },

    /**
     * バフ名から定義データを検索して返すヘルパー関数
     * @param {string} name - バフの内部ID名
     * @returns {object|null} 定義オブジェクト、または見つからない場合はnull
     */
    get: function(name) {
        // まずBUFFSから検索
        if (this.BUFFS[name]) return this.BUFFS[name];
        // 次にDEBUFFSから検索
        if (this.DEBUFFS[name]) return this.DEBUFFS[name];

        return null;
    }
};