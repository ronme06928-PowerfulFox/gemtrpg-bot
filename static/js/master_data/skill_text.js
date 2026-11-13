(function () {
  // 補正なしの定型文は読み取りの前に除く。
  function createReader(references = {}) {
    const REF = references;
    const LINK_REF_CACHE = {
      glossaryById: new Map((REF.glossary_refs || []).map(row=>[row.id || row.term_id, row.display_name || row.name || row.id])),
      skillById: new Map((REF.skill_refs || []).map(row=>[row.id,row.name || row.id])),
    };
    const NL_TIMING_MAP = [
      { key: "ラウンド終了時", timing: "END_ROUND" },
      { key: "マッチ終了時", timing: "END_MATCH" },
      { key: "使用時", timing: "PRE_MATCH" },
      { key: "的中時", timing: "HIT" },
      { key: "勝利時", timing: "WIN" },
      { key: "敗北時", timing: "LOSE" }
    ];
    const NL_FORBIDDEN_TIMING_WORDS = ["中時", "命中時"];
    const NL_TIMING_ALIASES = [
      { key: "マッチ勝利時", timing: "WIN" },
      { key: "マッチ敗北時", timing: "LOSE" },
      { key: "戦闘開始時", timing: "RESOLVE_START" },
      { key: "解決フェーズ開始時", timing: "RESOLVE_START" },
      { key: "即時発動", timing: "PRE_MATCH" },
      { key: "一方攻撃時", timing: "UNOPPOSED" }
    ];

    function _resolveLinkRefLabel(rawRef, explicitLabel){
      const label=String(explicitLabel||"").trim();
      if(label) return label;
      const ref=String(rawRef||"").trim();
      if(!ref) return "";
      const skillMatch=ref.match(/^skill\s*:\s*(.+)$/i);
      if(skillMatch){
        const sid=String(skillMatch[1]||"").trim();
        return LINK_REF_CACHE.skillById.get(sid) || sid;
      }
      return LINK_REF_CACHE.glossaryById.get(ref) || ref;
    }
    function _normalizeGlossaryMarkup(raw){
      let s=String(raw??"");
      const resolveInner=(inner)=>{
        const body=String(inner||"").trim();
        if(!body) return "";
        const sep=body.search(/[|｜]/);
        if(sep>=0){
          return _resolveLinkRefLabel(body.slice(0,sep), body.slice(sep+1));
        }
        return _resolveLinkRefLabel(body, "");
      };
      s=s.replace(/\[\[([^[\]]+?)\]\]/g,(_m,inner)=>resolveInner(inner));
      s=s.replace(/\[([^[\]]+?)\]/g,(_m,inner)=>resolveInner(inner));
      return s;
    }

    function _nlNormalizeWideChars(s){
      return String(s||"")
        .replace(/[０-９]/g, (d) => String.fromCharCode(d.charCodeAt(0) - 0xFEE0))
        .replace(/＋/g, "+")
        .replace(/－/g, "-");
    }
    function _nlContainsForbiddenTimingWord(raw){
      const s=String(raw||"").replace(/的中時/g,"");
      return NL_FORBIDDEN_TIMING_WORDS.find((w)=>s.includes(w)) || "";
    }
    function _nlCleanLine(raw){
      let s=_nlNormalizeWideChars(_normalizeGlossaryMarkup(String(raw||"").trim()));
      s=s.replace(/[【】]/g,"").replace(/（/g,"(").replace(/）/g,")");
      s=s.replace(/\s+/g," ");
      return s.trim();
    }
    function _nlSplitLines(rawText){
      const text=String(rawText||"").replace(/\r\n/g,"\n");
      if(!text.trim()) return { lines: [], errors: [] };
      const errors=[];
      if(text.includes("／")){
        errors.push("区切り記号は `。` と改行のみ使用できます（`／`は不可）。");
      }
      const lines=text
        .split(/[。\n]/)
        .map(_nlCleanLine)
        .filter(Boolean);
      return { lines, errors };
    }
    function _nlExtractTiming(sentence){
      const ng=_nlContainsForbiddenTimingWord(sentence);
      if(ng) return { error: '禁止語彙 ' + "'" + ng + "' を検出しました。'的中時' を使用してください。" };
      const src=String(sentence||"").trim();
      const start=src.replace(/^\(+\s*/,"");
      const hit=[...NL_TIMING_ALIASES, ...NL_TIMING_MAP].find(row=>start.startsWith(row.key));
      if(!hit) return {};
      const body=_nlCleanLine(src.slice(src.indexOf(hit.key)+hit.key.length).replace(/^[\]\)\s:：-]+/,""));
      if(!body) return { error: "timing '" + hit.key + "' の後に効果本文がありません" };
      return { timing: hit.timing, body };
    }

    function _nlComparison(word){
      if(word==="以下") return "LTE";
      if(/より(?:高い|大きい)/.test(word)) return "GT";
      if(/未満|より(?:低い|小さい)|以上ない/.test(word)) return "LT";
      return "GTE";
    }

    function _nlLeadingCondition(body){
      const match=body.match(/^(自分|自身|対象|相手)(?:の|に)(?:(?:このラウンド(?:の|における)))?(速度値|FP|MP|HP|出血|破裂|亀裂|戦慄|荊棘|蓄力|凝魔)(?:威力)?が\s*(?:(\d+)\s*(以上ない|以上(?:ある)?|以下|未満|より高い|より大きい|より低い|より小さい)|(ある|ない))なら[、,，]?\s*(.+)$/);
      if(!match) return {body};
      const [,who,param,value,comparison,exists,rest]=match;
      return {body:rest, condition:{
        source:/自分|自身/.test(who) ? "self" : "target",
        param:/蓄力|凝魔/.test(param) ? param+"_count" : param,
        operator:exists==="ない" ? "EQUALS" : _nlComparison(comparison || ""),
        value:exists==="ない" ? 0 : exists==="ある" ? 1 : Number(value)
      }};
    }
    function _nlPushError(list,column,line,reason){
      list.push({ column, line, reason });
    }
    function _nlParseCosts(lines, errors){
      const costs=[];
      lines.forEach((line)=>{
        const ng=_nlContainsForbiddenTimingWord(line);
        if(ng){
          _nlPushError(errors,"コスト",line,`禁止語彙（${ng}）を含んでいます。`);
          return;
        }
        const matches=[...line.matchAll(/(FP|MP|HP)\s*を\s*(\d+)\s*消費/g)];
        if(!matches.length){
          _nlPushError(errors,"コスト",line,"コストを解釈できません。例: FPを2消費");
          return;
        }
        matches.forEach((m)=>{
          const type=String(m[1]||"").trim();
          const value=Number(m[2]);
          if(!Number.isFinite(value) || value<=0){
            _nlPushError(errors,"コスト",line,"消費値は1以上の整数で指定してください。");
            return;
          }
          costs.push({ type, value });
        });
      });
      return costs;
    }
    function _nlResolveBuffIdByName(rawName){
      const name=String(rawName||"").replace(/[「」"']/g,"").trim();
      if(!name) return "";
      const refs=Array.isArray(REF.buff_refs)?REF.buff_refs:[];
      const exact=refs.find((b)=>String(b?.name||"").trim()===name);
      if(exact?.id) return String(exact.id);
      const starts=refs.find((b)=>String(b?.name||"").trim().startsWith(name));
      if(starts?.id) return String(starts.id);
      const fallback={
        "加速":"Bu-11",
        "減速":"Bu-12",
        "挑発":"Bu-01",
        "行動不能":"Bu-04",
        "出血遷延":"Bu-08",
        "蓄力":"Bu-30",
        "凝魔":"Bu-31",
        "震盪":"Bu-29"
      };
      return String(fallback[name]||"");
    }
    function _nlResolveSummonTemplate(rawName, errors, columnName, rawLine){
      const name=String(rawName||"").replace(/[「」"']/g,"").trim();
      if(!name){
        _nlPushError(errors,columnName,rawLine,"召喚テンプレート名またはIDが必要です。");
        return null;
      }
      const refs=Array.isArray(REF.summon_refs)?REF.summon_refs:[];
      const matches=refs.filter((row)=>{
        const id=String(row?.id||"").trim();
        const displayName=String(row?.name||"").trim();
        return id===name || displayName===name;
      });
      if(matches.length===0){
        _nlPushError(errors,columnName,rawLine,`召喚テンプレート「${name}」は登録されていません。`);
        return null;
      }
      if(matches.length>1){
        _nlPushError(errors,columnName,rawLine,`召喚テンプレート「${name}」が複数一致しました。IDで指定してください。`);
        return null;
      }
      return matches[0];
    }
    function _nlExtractStackSumStateNames(rawText){
      const src=String(rawText||"");
      const rows=[...src.matchAll(/(出血|破裂|亀裂|戦慄|荊棘)/g)].map((m)=>String(m[1]||""));
      const names=[];
      rows.forEach((name)=>{ if(name && !names.includes(name)) names.push(name); });
      return names;
    }
    function _nlBuildStackSumParam(rawText){
      const names=_nlExtractStackSumStateNames(rawText);
      if(!names.length) return "";
      return `状態異常スタック合計:${names.join(",")}`;
    }
    function _nlParseTriggerLine(rawLine, errors, columnName, inheritedTiming="HIT"){
      if(/この効果で付与されたスキルは\d+回まで使用可能/.test(rawLine)) return [];
      if(/(蓄力|凝魔).*不足.*効果は発生しない/.test(rawLine)) return [];
      const t=_nlExtractTiming(rawLine);
      if(t.error){
        _nlPushError(errors,columnName,rawLine,t.error);
        return null;
      }
      t.timing ??= inheritedTiming;
      const {body,condition:leadingCondition}=_nlLeadingCondition(t.body ?? rawLine);
      const explicitTarget=body.includes("対象") || body.includes("相手");
      const explicitSelf=body.includes("自分") || body.includes("自身");
      const target=explicitTarget ? "target" : "self";
      const defaultApplyTarget=explicitSelf ? "self" : "target";

      let m;
      const out=[];
      const seen=new Set();
      const add=(e)=>{
        if(!e) return;
        if(leadingCondition && !e.condition) e.condition=leadingCondition;
        const sig=JSON.stringify(e);
        if(seen.has(sig)) return;
        seen.add(sig);
        out.push(e);
      };
      if(/^\d+\s*ラウンド継続$/.test(body)) return out;
      if(/^\(最大(?:で)?\s*\d+\)?$/.test(body)) return out;


      m=body.match(/(?:自分|自身)(?:に|は|が)?\s*(\d+)\s*ダメージ(?:を)?(?:受ける|受け|被る|くらう)|(?:自分|自身)に\s*(\d+)\s*ダメージ/);
      if(m){
        const selfDamage = Number(m[1] || m[2] || 0);
        if(selfDamage > 0) add({ timing:t.timing, type:"APPLY_STATE", target:"self", state_name:"HP", value:-selfDamage });
      }
      m=body.match(/付与から数えて(\d+)回目のラウンド終了時に自身に破裂爆発を起こす[」"]状態を与える/);
      if(m){
        add({ timing:t.timing, type:"APPLY_BUFF", target:"target", buff_id:"Bu-07", delay:Number(m[1]), lasting:0 });
        return out;
      }
      m=body.match(/(\d+)\s*スタックの震盪を付与/);
      if(m){
        add({ timing:t.timing, type:"APPLY_BUFF", target:defaultApplyTarget, buff_id:_nlResolveBuffIdByName("震盪"), count:Number(m[1]) });
        return out;
      }
      m=body.match(/(\d+)\s*ラウンドの出血遷延を付与/);
      if(m && !/消費/.test(body)){
        add({ timing:t.timing, type:"APPLY_BUFF", target:defaultApplyTarget, buff_id:"Bu-08", count:Number(m[1]) });
        return out;
      }
      if(body.includes("亀裂崩壊")){
        const dmg=body.match(/(\d+)\s*ダメージ/);
        add({ timing: t.timing, type: "CUSTOM_EFFECT", target: "target", value: "亀裂崩壊_DAMAGE", damage_per_fissure: dmg?Number(dmg[1]):3 });
      }
      if(body.includes("破裂爆発")){
        const ruptureBurst={ timing:t.timing, type:"CUSTOM_EFFECT", target:"target", value:"破裂爆発" };
        const ruptureThreshold=body.match(/(?:対象|相手)の破裂が\s*(\d+)\s*以上なら/);
        if(ruptureThreshold){
          ruptureBurst.condition={ source:"target", param:"破裂", operator:"GTE", value:Number(ruptureThreshold[1]) };
        }
        add(ruptureBurst);
      }

      m=body.match(/対象の(?:特徴|タグ)に[「"]([^」"]+)[」"]があるなら[、,，]?\s*(\d+)\s*ダメージを与える/);
      if(m){
        add({
          timing:t.timing,
          type:"DAMAGE_BONUS",
          target:"target",
          value:Number(m[2]),
          condition:{ source:"target", param:"tag_ids", operator:"CONTAINS", value:m[1] }
        });
        return out;
      }

      m=body.match(/次のラウンド開始時[、,，]?\s*[「"]([^」"]+)[」"]\s*(\d+)\s*体を召喚する/);
      if(m){
        const summon=_nlResolveSummonTemplate(m[1],errors,columnName,rawLine);
        if(!summon) return null;
        add({
          timing:"RESOLVE_START",
          type:"SCHEDULE_EFFECT",
          target:"self",
          round_offset:1,
          repeat_count:Number(m[2]),
          effect:{ type:"SUMMON_CHARACTER", summon_template_id:String(summon.id) }
        });
        return out;
      }

      m=body.match(/フィールドに存在する全ての[「"]([^」"]+)[」"]のHPを0にする/);
      if(m){
        const summon=_nlResolveSummonTemplate(m[1],errors,columnName,rawLine);
        if(!summon) return null;
        const tagIds=Array.isArray(summon.tag_ids)
          ? summon.tag_ids.map((tag)=>String(tag||"").trim()).filter(Boolean)
          : [];
        if(!tagIds.length){
          _nlPushError(errors,columnName,rawLine,`召喚テンプレート「${m[1]}」にtag_idsがありません。`);
          return null;
        }
        add({
          timing:"RESOLVE_START",
          type:"CUSTOM_EFFECT",
          target:"FILTERED_CHARACTERS",
          value:"DEAL_TARGET_MAX_HP_DAMAGE",
          character_filter:{
            team:"same_team",
            required_tag_ids:tagIds,
            alive:true,
            placed:true
          }
        });
        return out;
      }

      m=body.match(/存在していた[「"]([^」"]+)[」"]が1体につき\s*(\d+)[、,，]?\s*このラウンドで(?:自分|自身)が使うスキルの最終威力をアップする/);
      if(m){
        const summon=_nlResolveSummonTemplate(m[1],errors,columnName,rawLine);
        if(!summon) return null;
        const tagIds=Array.isArray(summon.tag_ids)
          ? summon.tag_ids.map((tag)=>String(tag||"").trim()).filter(Boolean)
          : [];
        if(!tagIds.length){
          _nlPushError(errors,columnName,rawLine,`召喚テンプレート「${m[1]}」にtag_idsがありません。`);
          return null;
        }
        add({
          timing:"RESOLVE_START",
          type:"APPLY_BUFF_FROM_CHARACTER_COUNT",
          target:"self",
          buff_name:`${String(summon.name||summon.id)}吸収`,
          lasting:1,
          delay:0,
          value_per_character:Number(m[2]),
          apply_to:"final",
          character_filter:{
            team:"same_team",
            required_tag_ids:tagIds,
            alive:true,
            placed:true
          }
        });
        return out;
      }
      if(body.includes("出血氾濫")) add({ timing: t.timing, type: "CUSTOM_EFFECT", target: /(?:自分|自身)に出血氾濫/.test(body) ? "self" : "target", value: "出血氾濫" });
      if(body.includes("戦慄殺到")) add({ timing: t.timing, type: "CUSTOM_EFFECT", target: "target", value: "戦慄殺到" });
      if(body.includes("荊棘飛散")) add({ timing: t.timing, type: "CUSTOM_EFFECT", target: "target", value: "荊棘飛散" });

      m=body.match(/(?:対象|相手)の(?:特徴|タグ)に\s*[「『"“]?([^」』"”]+?)[」』"”]?\s*(?:がある|が含まれる|を持つ|を持っている)なら.*?(?:その|対象の|相手の)?最大HPと(?:同じ値|同値)のダメージ/);
      if(m){
        const tagName=String(m[1]||"").trim();
        if(tagName){
          add({
            timing:t.timing,
            type:"CUSTOM_EFFECT",
            target:"target",
            value:"DEAL_TARGET_MAX_HP_DAMAGE",
            condition:{ source:"target", param:"tag_ids", operator:"CONTAINS", value:tagName }
          });
        }
      }
      if(body.includes("血漿転化")){
        add({
          timing:t.timing,
          type:"CONVERT_STACK_RESOURCE_VARIANT",
          target:"self",
          buff_name:"凝魔",
          to_variant:"blood_plasma",
          require_count_gte:1
        });
      }
      if(body.includes("爆破誘導") || body.includes("W-81")){
        add({
          timing:t.timing,
          type:"CONVERT_STACK_RESOURCE_VARIANT",
          target:"self",
          buff_name:"蓄力",
          to_variant:"burst_guidance",
          require_count_gte:1
        });
      }
      if(out.length && !/を付与|を得る|ダメージ|減少|回復|解除|再使用/.test(body)) return out;

      m=body.match(/(対象|相手)の([出血破裂亀裂戦慄荊棘・、，,\/\sと及び]+)の合計\s*(\d+)\s*につき\s*(\d+)\s*[、,，]\s*(自分|自身|対象|相手)の?(FP|MP|HP)\s*を?\s*回復/);
      if(m){
        const sourceParam=_nlBuildStackSumParam(m[2]);
        const recoverTarget=(m[5]==="自分"||m[5]==="自身")?"self":"target";
        if(sourceParam){
          add({
            timing: t.timing,
            type: "APPLY_STATE_PER_N",
            target: recoverTarget,
            source: "target",
            source_param: sourceParam,
            per_N: Number(m[3]),
            state_name: m[6],
            value: Number(m[4]),
          });
        }
      }
      m=body.match(/(対象|相手)の([出血破裂亀裂戦慄荊棘・、，,\/\sと及び]+)の合計(?:値)?\s*(\d+)\s*につき\s*(\d+)\s*[、,，]?\s*(蓄力|凝魔)\s*を得る(?:.*?最大(?:で)?\s*(\d+))?/);
      if(m){
        const sourceParam=_nlBuildStackSumParam(m[2]);
        const perN=Number(m[3]);
        const gainPerStep=Number(m[4]);
        const buffName=String(m[5]||"").trim();
        const buffId=_nlResolveBuffIdByName(buffName);
        const maxCount=Math.max(1, Number(m[6]||9999));
        if(sourceParam && buffId && perN>0 && gainPerStep>0){
          add({
            timing:t.timing,
            type:"APPLY_BUFF_PER_N",
            target:"self",
            source:"target",
            source_param:sourceParam,
            per_N:perN,
            value:gainPerStep,
            buff_id:buffId,
            max_count:maxCount
          });
        }
      }
      m=body.match(/(?:自分|自身)の?失ったHP\s*(\d+)\s*につき[、,，]?\s*(蓄力|凝魔)\s*(\d+)\s*を得る(?:.*?最大(?:で)?\s*(\d+))?/);
      if(m){
        const perN=Number(m[1]);
        const buffName=String(m[2]||"").trim();
        const gainPerStep=Number(m[3]);
        const buffId=_nlResolveBuffIdByName(buffName);
        const maxCount=Math.max(1, Number(m[4]||9999));
        if(buffId && perN>0 && gainPerStep>0){
          add({
            timing:t.timing,
            type:"APPLY_BUFF_PER_N",
            target:"self",
            source:"self",
            source_param:"lost_hp",
            per_N:perN,
            value:gainPerStep,
            buff_id:buffId,
            max_count:maxCount
          });
        }
      }
      m=body.match(/(?:自分|自身)の?失ったHP\s*(\d+)\s*につき\s*(\d+)\s*[、,，]?\s*(蓄力|凝魔)\s*を得る(?:.*?最大(?:で)?\s*(\d+))?/);
      if(m){
        const perN=Number(m[1]);
        const gainPerStep=Number(m[2]);
        const buffName=String(m[3]||"").trim();
        const buffId=_nlResolveBuffIdByName(buffName);
        const maxCount=Math.max(1, Number(m[4]||9999));
        if(buffId && perN>0 && gainPerStep>0){
          add({
            timing:t.timing,
            type:"APPLY_BUFF_PER_N",
            target:"self",
            source:"self",
            source_param:"lost_hp",
            per_N:perN,
            value:gainPerStep,
            buff_id:buffId,
            max_count:maxCount
          });
        }
      }

      m=body.match(/対象の(出血|破裂|亀裂|戦慄)\s*(\d+)\s*につき.*?(出血|破裂|亀裂|戦慄)\s*(\d+)\s*を付与(?:\s*\(?最大(?:で)?\s*(\d+)\)?)?/);
      if(m){
        const row={ timing: t.timing, type: "APPLY_STATE_PER_N", target: "target", source: "target", source_param: m[1], per_N: Number(m[2]), state_name: m[3], value: Number(m[4]) };
        if(m[5]) row.max_value=Number(m[5]);
        add(row);
        return out;
      }
      m=body.match(/(自分|自身)の(出血|破裂|亀裂|戦慄)\s*(\d+)\s*につき\s*(\d+)\s*の(\d+)\s*ラウンド継続する(出血|破裂|亀裂|戦慄)\s*を付与/);
      if(m){
        add({ timing:t.timing, type:"APPLY_STATE_PER_N", target:"target", source:"self", source_param:m[2], per_N:Number(m[3]), state_name:m[6], value:Number(m[4]), rounds:Number(m[5]) });
      }

      let matchedConsumeApplyState = false;
      m=body.match(/(蓄力|凝魔)\s*(\d+)\s*を消費し[、,，]?\s*(?:(対象|相手|自分|自身)に?)?\s*(\d+)\s*ラウンド(?:の)?\s*(出血|破裂|亀裂|戦慄|荊棘)\s*(-?\d+)\s*を付与/);
      if(m){
        const applyTargetWord = m[3] || "";
        const applyTarget = (applyTargetWord==="自分" || applyTargetWord==="自身") ? "self" : "target";
        add({
          timing:t.timing,
          type:"CONSUME_BUFF_COUNT_FOR_GAIN",
          target:"self",
          buff_name:m[1],
          consume_required:Math.max(1, Number(m[2])),
          gains:[{
            type:"APPLY_STATE",
            target:applyTarget,
            state_name:m[5],
            value:Number(m[6]),
            rounds:Math.max(1, Number(m[4]))
          }]
        });
        matchedConsumeApplyState = true;
      }

      m=body.match(/(\d+)\s*ラウンド.*?(出血|破裂|亀裂|戦慄|荊棘)\s*(-?\d+)\s*を付与/);
      let matchedRoundStateApply = false;
      if(m && !matchedConsumeApplyState){
        matchedRoundStateApply = true;
        add({ timing: t.timing, type: "APPLY_STATE", target: defaultApplyTarget, state_name: m[2], value: Number(m[3]), rounds: Number(m[1]) });
      }

      m=body.match(/(出血|破裂|亀裂|戦慄|荊棘|FP|MP|HP)\s*(-?\d+)\s*を付与/);
      if(m && !matchedRoundStateApply && !matchedConsumeApplyState){
        add({ timing: t.timing, type: "APPLY_STATE", target: defaultApplyTarget, state_name: m[1], value: Number(m[2]) });
      }
      m=body.match(/(出血|破裂|亀裂|戦慄|荊棘|FP|MP|HP)\s*(-?\d+)\s*を与える/);
      if(m){
        add({ timing: t.timing, type: "APPLY_STATE", target, state_name: m[1], value: Number(m[2]) });
      }

      let matchedConsumeGain = false;
      m=body.match(/(蓄力|凝魔)\s*(?:(\d+)\s*を|を\s*(\d+))\s*消費し[、,，]?\s*(?:(?:自分|自身)の)?\s*(FP|MP|HP)\s*を\s*(-?\d+)\s*(得る|獲得|回復)/);
      if(m){
        const consumeN=Math.max(1, Number(m[2] || m[3]));
        const gainType=m[4];
        const gainValue=Number(m[5]);
        if(Number.isFinite(gainValue)){
          add({
            timing:t.timing,
            type:"CONSUME_BUFF_COUNT_FOR_GAIN",
            target:"self",
            buff_name:m[1],
            consume_required:consumeN,
            gains:[{ type:gainType, value:gainValue }]
          });
          matchedConsumeGain = true;
        }
      }
      m=body.match(/(FP|MP|HP)\s*を\s*(-?\d+)\s*得る/);
      if(m && !matchedConsumeGain){
        add({ timing: t.timing, type: "APPLY_STATE", target, state_name: m[1], value: Number(m[2]) });
      }
      m=body.match(/(FP|MP|HP)\s*を\s*(-?\d+)\s*獲得/);
      if(m && !matchedConsumeGain){
        add({ timing: t.timing, type: "APPLY_STATE", target, state_name: m[1], value: Number(m[2]) });
      }
      m=body.match(/(MP|HP)\s*を\s*(\d+)\s*回復/);
      if(m && !matchedConsumeGain){
        add({ timing: t.timing, type: "APPLY_STATE", target, state_name: m[1], value: Number(m[2]) });
      }
      m=body.match(/(MP|HP)\s*を\s*(\d+)\s*減少/);
      if(m){
        add({ timing: t.timing, type: "APPLY_STATE", target: "target", state_name: m[1], value: -Number(m[2]) });
      }
      if(body.includes("減少させた分だけ自身のMPを回復する")){
        add({ timing: t.timing, type: "APPLY_STATE", target: "self", state_name: "MP", value: 6 });
      }
      m=body.match(/次にこのキャラクターが付与する亀裂の値\+?(\d+)/);
      if(m){
        add({ timing:t.timing, type:"APPLY_BUFF", target:"self", buff_id:"Bu-41", lasting:999, count:1, data:{ value:Number(m[1]), display_name:"突き崩す（亀裂付与量アップ単発）" } });
      }
      if(body.includes("与えたダメージの値") && body.includes("HPを回復")){
        add({ timing: t.timing, type: "DRAIN_HP", target: "self", value: 1 });
      }

      let matchedConsumeApplyBuff = false;
      m=body.match(/(蓄力|凝魔)\s*(\d+)\s*を消費し[、,，]?\s*(?:(対象|相手|自分|自身)に?)?\s*(\d+)\s*ラウンド(?:の)?\s*(加速|減速|挑発|行動不能|震盪|蓄力|凝魔|出血遷延)\s*を付与/);
      if(m){
        const consumeBuffName = m[1];
        const consumeRequired = Math.max(1, Number(m[2]));
        const applyTargetWord = m[3] || "";
        const applyRounds = Math.max(1, Number(m[4]));
        const applyBuffName = m[5];
        const applyTarget = (applyTargetWord==="自分" || applyTargetWord==="自身") ? "self" : "target";
        const applyBuffId = _nlResolveBuffIdByName(applyBuffName);
        if(applyBuffId){
          add({
            timing:t.timing,
            type:"CONSUME_BUFF_COUNT_FOR_GAIN",
            target:"self",
            buff_name:consumeBuffName,
            consume_required:consumeRequired,
            gains:[{
              type:"APPLY_BUFF",
              target:applyTarget,
              buff_id:applyBuffId,
              lasting:applyRounds
            }]
          });
          matchedConsumeApplyBuff = true;
        }
      }

      m=body.match(/(Bu-\d+)\s*を付与/);
      if(m){
        const row={ timing: t.timing, type: "APPLY_BUFF", target: defaultApplyTarget, buff_id: m[1] };
        const lasting=body.match(/(\d+)\s*ラウンド/);
        if(lasting) row.lasting=Number(lasting[1]);
        const count=body.match(/(\d+)\s*スタック/);
        if(count) row.data={ count: Number(count[1]) };
        add(row);
      }
      m=body.match(/(Bu-\d+)\s*を解除/);
      if(m){
        add({ timing: t.timing, type: "REMOVE_BUFF", target, buff_id: m[1] });
      }
      let matchedConditionalStackBuffGain = false;
      m=body.match(/(?:対象|相手)(?:に|の)?(出血|破裂|亀裂|戦慄|荊棘)(?:が\s*(\d+)\s*以上|がある)なら.*?(蓄力|凝魔)\s*(\d+)\s*を(付与|得る|獲得)/);
      if(m){
        const bId=_nlResolveBuffIdByName(m[3]);
        if(bId){
          add({
            timing:t.timing,
            type:"APPLY_BUFF",
            target:(m[5]==="得る" || m[5]==="獲得" || /自分|自身/.test(body)) ? "self" : "target",
            buff_id:bId,
            data:{ count:Number(m[4]) },
            condition:{ source:"target", param:m[1], operator:"GTE", value:Number(m[2]||1) }
          });
          matchedConditionalStackBuffGain = true;
        }
      }
      m=body.match(/\[\[[^\]]*?(加速|減速|挑発|行動不能|震盪|蓄力|凝魔|出血遷延)[^\]]*?\]\]\s*を?\s*(\d+)?\s*(付与|得る)/);
      if(!m){
        m=body.match(/(加速|減速|挑発|行動不能|震盪|蓄力|凝魔|出血遷延)\s*(\d+)?\s*を(付与|得る)/);
      }
      if(!m){
        m=body.match(/(加速|減速|挑発|行動不能|震盪|蓄力|凝魔|出血遷延)\s*を?\s*(\d+)\s*(付与|得る)/);
      }
      if(m){
        // "Xにつき...蓄力を得る" は APPLY_BUFF_PER_N で先に解釈済み。
        // ここで no-count の蓄力/凝魔を拾うと重複付与になるため抑止する。
        if(!m[2] && /につき/.test(body) && (m[1]==="蓄力" || m[1]==="凝魔")){
          m = null;
        }
      }
      if(m && !matchedConsumeApplyBuff && !matchedConditionalStackBuffGain){
        const bId=_nlResolveBuffIdByName(m[1]);
        if(bId){
          const action = m[3];
          const count = m[2];
          const row={ timing:t.timing, type:"APPLY_BUFF", target:action==="得る"?"self":defaultApplyTarget, buff_id:bId };
          if(count) row.data={ count:Number(count) };
          if(/次のラウンド/.test(body)){ row.lasting=1; row.delay=1; }
          add(row);
        }
      }
      m=body.match(/対象に(\d+)\s*ダメージ/);
      if(m){
        add({ timing:t.timing, type:"DAMAGE_BONUS", target:"target", value:Number(m[1]) });
      }
      m=body.match(/消費した亀裂\s*(\d+)\s*につき\s*(\d+)\s*ダメージ/);
      if(m){
        const per=Math.max(1, Number(m[1]));
        const dmg=Number(m[2]);
        add({ timing:t.timing, type:"CUSTOM_EFFECT", target:"target", value:"亀裂崩壊_DAMAGE", damage_per_fissure: Math.max(1, Math.floor(dmg/per)) });
      }
      m=body.match(/^(\d+)\s*ダメージ(?:を与える)?$/);
      if(m && leadingCondition){
        add({ timing:t.timing, type:"DAMAGE_BONUS", target:"target", value:Number(m[1]) });
      }
      if(/行動不能になる/.test(body)){
        add({ timing:t.timing, type:"APPLY_BUFF", target:"self", buff_id:"Bu-04", lasting:1, delay:1 });
      }
      for(const correction of body.matchAll(/(?:(自分|自身|対象|相手)の)?(物理補正|魔法補正)\s*([+\-−]\s*\d+)/g)){
        const [,who,stat,delta]=correction;
        const val=Number(delta.replace(/\s+/g,"").replace("−","-"));
        const buffId=stat==="物理補正" ? (val>=0?"Bu-36":"Bu-37") : (val>=0?"Bu-38":"Bu-39");
        const row={ timing:t.timing, type:"APPLY_BUFF", target:/対象|相手/.test(who || "")?"target":"self", buff_id:buffId, data:{ value:Math.abs(val) } };
        const lasting=body.match(/(\d+)\s*ラウンド後まで/);
        const delay=body.match(/(\d+)\s*ラウンド後に/);
        if(lasting) row.lasting=Number(lasting[1])+1;
        else if(delay || /次のラウンド/.test(body)){
          row.lasting=1;
          row.delay=delay ? Number(delay[1]) : 1;
        }
        add(row);
      }
      m=body.match(/対象が守備スキルを使用しているとき.*?基礎威力\s*([+\-−]\s*\d+)/);
      if(m){
        add({ timing:t.timing, type:"MODIFY_BASE_POWER", target:"target", value:Number(String(m[1]).replace(/\s+/g,"").replace("−","-")), condition:{ source:"target_skill", param:"tags", operator:"CONTAINS", value:"守備" } });
      }
      m=body.match(/対象に.*?被ダメージ時.*?出血\s*(\d+)\s*を得る.*?状態/);
      if(m){
        add({ timing:t.timing, type:"APPLY_BUFF", target:"target", buff_id:"Bu-47", data:{ value:Number(m[1]), display_name:"抉られた傷" } });
      }
      m=body.match(/(蓄力|凝魔)\s*(\d+)\s*を消費し.*?(基礎威力|最終威力)\s*([+\-−]\s*\d+)/);
      if(m){
        const buffName=m[1];
        const consumeN=Math.max(1, Number(m[2]));
        const applyTo=m[3].includes("最終")?"final":"base";
        const delta=Number(String(m[4]).replace(/\s+/g,"").replace("−","-"));
        if(Number.isFinite(delta) && delta!==0){
          if(delta % consumeN === 0){
            add({
              timing:t.timing,
              type:"CONSUME_BUFF_COUNT_FOR_POWER",
              target:"self",
              buff_name:buffName,
              consume_max:consumeN,
              value_per_stack:(delta/consumeN),
              apply_to:applyTo,
              min_consume:consumeN
            });
          }else{
            add({
              timing:t.timing,
              type:applyTo==="final"?"MODIFY_FINAL_POWER":"MODIFY_BASE_POWER",
              target:"self",
              value:delta,
              condition:{ source:"self", param:`${buffName}_count`, operator:"GTE", value:consumeN }
            });
            add({
              timing:t.timing,
              type:"CONSUME_BUFF_COUNT_FOR_GAIN",
              target:"self",
              buff_name:buffName,
              consume_required:consumeN,
              gains:[]
            });
          }
        }
      }
      m=body.match(/使用する(攻撃|守備)スキルの最終威力\s*([+\-−]\s*\d+)/);
      if(m){
        const val=Number(String(m[2]).replace(/\s+/g,"").replace("−","-"));
        const buffId=(m[1]==="攻撃") ? (val>=0?"Bu-32":"Bu-34") : (val>=0?"Bu-33":"Bu-35");
        add({ timing:t.timing, type:"APPLY_BUFF", target:"self", buff_id:buffId, data:{ value:Math.abs(val) }, lasting:1, delay:0 });
      }
      m=body.match(/(攻撃|守備)スキルの威力\s*([+\-−]\s*\d+)/);
      if(m){
        const val=Number(String(m[2]).replace(/\s+/g,"").replace("−","-"));
        const buffId=(m[1]==="攻撃") ? (val>=0?"Bu-32":"Bu-34") : (val>=0?"Bu-33":"Bu-35");
        add({ timing:t.timing, type:"APPLY_BUFF", target:body.includes("対象")?"target":"self", buff_id:buffId, data:{ value:Math.abs(val) }, lasting:1, delay:0 });
      }
      m=body.match(/[「"]([^」"]+)[」"]\s*(\d+)?\s*体?を召喚する/);
      if(m){
        const summon=_nlResolveSummonTemplate(m[1],errors,columnName,rawLine);
        if(!summon) return null;
        add({
          timing:t.timing,
          type:"SUMMON_CHARACTER",
          target:"self",
          summon_template_id:String(summon.id),
          repeat_count:Number(m[2]||1)
        });
      }else if(/召喚する/.test(body)){
        _nlPushError(errors,columnName,rawLine,"召喚テンプレート名と個数を明記してください。");
        return null;
      }
      m=body.match(/味方全体.*?([A-Z]-\d+).*?伝授.*?(\d+)回まで/);
      if(m){
        add({ timing:t.timing, type:"GRANT_SKILL", target:"ALL_OTHER_ALLIES", skill_id:m[1], grant_mode:"usage_count", uses:Number(m[2]), overwrite:true });
      }
      m=body.match(/味方全体.*?([A-Z]-\d+).*?伝授/);
      if(m){
        add({ timing:t.timing, type:"GRANT_SKILL", target:"ALL_OTHER_ALLIES", skill_id:m[1], grant_mode:"usage_count", uses:2, overwrite:true });
      }
      m=body.match(/自分の(出血|破裂|亀裂|戦慄)の二倍の値の(出血|破裂|亀裂|戦慄)を対象に付与/);
      if(m){
        add({ timing:t.timing, type:"APPLY_STATE_PER_N", target:"target", source:"self", source_param:m[1], per_N:1, state_name:m[2], value:2 });
      }
      m=body.match(/(対象|相手)の(出血|破裂|亀裂|戦慄)威力を2倍にする/);
      if(m){
        add({ timing:t.timing, type:"MULTIPLY_STATE", target:"target", state_name:m[2], value:2.0 });
      }
      m=body.match(/自分の凝魔を可能な限り消費し\(最大で(\d+)\).*?最終威力を上昇/);
      if(m){
        add({ timing:t.timing, type:"CONSUME_BUFF_COUNT_FOR_POWER", target:"self", buff_name:"凝魔", consume_max:Number(m[1]), value_per_stack:1, apply_to:"final", min_consume:1 });
      }
      m=body.match(/このラウンドで自分が付与する亀裂の値に\+?(\d+)/);
      if(m){
        add({ timing:t.timing, type:"APPLY_BUFF", target:"self", buff_id:"Bu-40", lasting:1, data:{ value:Number(m[1]) } });
      }
      m=body.match(/([^\s、。]+)\s*(\d+)\s*を(付与|得る)/);
      if(m && !/(出血|破裂|亀裂|戦慄|荊棘|FP|MP|HP|Bu-\d+|加速|減速|挑発|行動不能|震盪|蓄力|凝魔|出血遷延)/.test(m[1])){
        const bName=m[1];
        const bId=_nlResolveBuffIdByName(bName);
        if(bId){
          const row={ timing: t.timing, type: "APPLY_BUFF", target: m[3]==="得る"?"self":target, buff_id: bId, data:{ count: Number(m[2]) } };
          if(/次のラウンド/.test(body)){ row.lasting=1; row.delay=1; }
          const lasting=body.match(/(\d+)\s*ラウンド/);
          if(lasting && !row.lasting){ row.lasting=Number(lasting[1]); row.delay=0; }
          add(row);
        }
      }

      m=body.match(/受けるダメージを(\d+)%上げ/);
      if(m){
        const row={ timing:t.timing, type:"APPLY_BUFF", target:"target", buff_id:"Bu-43", data:{ value:Number(m[1]) } };
        if(/次のラウンド/.test(body)){ row.lasting=1; row.delay=1; }
        add(row);
      }
      m=body.match(/受けるダメージ\s*([+\-−]\s*\d+)\s*%/);
      if(m){
        const val=Number(String(m[1]).replace(/\s+/g,"").replace("−","-"));
        if(Number.isFinite(val)){
          const row={ timing:t.timing, type:"APPLY_BUFF", target:"target", buff_id:(val>=0?"Bu-43":"Bu-44"), data:{ value:Math.abs(val) } };
          if(/次のラウンド/.test(body)){ row.lasting=1; row.delay=1; }
          add(row);
        }
      }
      m=body.match(/受けるダメージを(\d+)%下げ/);
      if(m){
        const row={ timing:t.timing, type:"APPLY_BUFF", target:"target", buff_id:"Bu-44", data:{ value:Number(m[1]) } };
        if(/次のラウンド/.test(body)){ row.lasting=1; row.delay=1; }
        add(row);
      }
      m=body.match(/与えるダメージを(\d+)%上げ/);
      if(m){
        const row={ timing:t.timing, type:"APPLY_BUFF", target:"self", buff_id:"Bu-45", data:{ value:Number(m[1]) } };
        if(/次のラウンド/.test(body)){ row.lasting=1; row.delay=1; }
        add(row);
      }
      m=body.match(/与えるダメージ\s*([+\-−]\s*\d+)\s*%/);
      if(m){
        const val=Number(String(m[1]).replace(/\s+/g,"").replace("−","-"));
        if(Number.isFinite(val)){
          const row={ timing:t.timing, type:"APPLY_BUFF", target:"self", buff_id:(val>=0?"Bu-45":"Bu-46"), data:{ value:Math.abs(val) } };
          if(/次のラウンド/.test(body)){ row.lasting=1; row.delay=1; }
          add(row);
        }
      }
      m=body.match(/与えるダメージを(\d+)%下げ/);
      if(m){
        const row={ timing:t.timing, type:"APPLY_BUFF", target:"self", buff_id:"Bu-46", data:{ value:Number(m[1]) } };
        if(/次のラウンド/.test(body)){ row.lasting=1; row.delay=1; }
        add(row);
      }
      m=body.match(/ダメージ(?:固定)?\s*([+\-]\s*\d+|\d+)/);
      if(m){
        const hasSemanticDamageBuff = /受けるダメージ|与えるダメージ/.test(body);
        if(!hasSemanticDamageBuff){
          const n=Number(String(m[1]).replace(/\s+/g,""));
          if(Number.isFinite(n)) add({ timing: t.timing, type: "DAMAGE_BONUS", target: "target", value: n });
        }
      }
      if(body.includes("再使用")){
        const max=(body.match(/(\d+)(?:回|度)まで/)||[])[1];
        const fp=(body.match(/FPを(\d+)消費/)||[])[1];
        const stack=(body.match(/(凝魔|蓄力)(\d+)を消費/) || body.match(/(凝魔|蓄力)を(\d+)消費/));
        const row={ timing: t.timing, type: "USE_SKILL_AGAIN", target:stack?"self":"target", consume_cost:false, max_reuses:Number(max || 1) };
        if(fp) row.reuse_cost=[{ type:"FP", value:Number(fp) }];
        if(stack) row.stack_reuse_cost={ buff_name:stack[1], value:Number(stack[2]) };
        add(row);
      }

      if(/次のラウンド/.test(body)){
        out.forEach((e)=>{
          if(!e || e.type!=="APPLY_BUFF") return;
          e.lasting ??= 1;
          e.delay ??= 1;
        });
      }

      if(out.length) return out;
      _nlPushError(errors,columnName,rawLine,"効果を解釈できません。対応している文型で記述してください。");
      return null;
    }
    function _nlParseNotes(lines, errors){
      const pb=[];
      const effects=[];
      const tags=new Set();
      lines.forEach((line)=>{
        const limit=line.match(/^\(?最大(?:で)?\s*(\d+)\)?$/);
        const previous=pb.at(-1);
        if(limit && previous?.operation==="PER_N_BONUS"){
          if(previous.value>=0) previous.max_bonus=Number(limit[1]);
          else previous.min_bonus=-Number(limit[1]);
          return;
        }
        const ng=_nlContainsForbiddenTimingWord(line);
        if(ng){
          _nlPushError(errors,"特記",line,`禁止語彙（${ng}）を含んでいます。`);
          return;
        }
        if(/マッチ不可/.test(line)) tags.add("マッチ不可");
        if(/非ダメージ/.test(line)) tags.add("非ダメージ");
        if(/対象を選択しない/.test(line)) tags.add("自己対象");
        if(/宝石の加護/.test(line)) tags.add("宝石の加護スキル");
        if(/強硬スキル/.test(line)) tags.add("強硬");
        if(/牽制スキル/.test(line)) tags.add("牽制");
        if(/同陣営指定/.test(line)) tags.add("同陣営指定");
        if(/このスキルは対象を選択しない/.test(line)){ tags.add("自己対象"); return; }
        if(/非ダメージスキル/.test(line)){ tags.add("非ダメージ"); return; }
        if(/^\(?(宝石の加護|マッチ不可|強硬スキル|牽制スキル)\)?$/.test(line)) return;
        if(/^マッチ不可・非ダメージ$/.test(line)) return;
        if(/^同陣営指定スキル$/.test(line)) return;
        if(_nlExtractTiming(line).timing){
          const parsed=_nlParseTriggerLine(line, errors, "特記");
          if(parsed && parsed.length) effects.push(...parsed);
          return;
        }
        let m=line.match(/(対象|相手|メインターゲット)の([出血破裂亀裂戦慄荊棘・、，,\/\sと及び]+)の合計が?(\d+)以上(?:あるなら)?[、,，]?\s*(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)/);
        if(m){
          const applyTo=m[4].includes("ダイス")?"dice":(m[4].includes("最終")?"final":"base");
          const stackParam=_nlBuildStackSumParam(m[2]);
          if(stackParam){
            pb.push({
              operation:"FIXED",
              value:Number(String(m[5]).replace(/\s+/g,"").replace("−","-")),
              apply_to:applyTo,
              condition:{ source:"target", param:stackParam, operator:"GTE", value:Number(m[3]) }
            });
            return;
          }
        }
        m=line.match(/(対象|相手|メインターゲット)の([出血破裂亀裂戦慄荊棘・、，,\/\sと及び]+)の合計が?(\d+)\s*あるごとに.*?(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)(?:.*?最大(?:で)?\s*(\d+))?/);
        if(m){
          const applyTo=m[4].includes("ダイス")?"dice":(m[4].includes("最終")?"final":"base");
          const stackParam=_nlBuildStackSumParam(m[2]);
          if(stackParam){
            const row={
              operation:"PER_N_BONUS",
              source:"target",
              param:stackParam,
              per_N:Number(m[3]),
              value:Number(String(m[5]).replace(/\s+/g,"").replace("−","-")),
              apply_to:applyTo
            };
            if(m[6]){
              if(row.value>=0) row.max_bonus=Number(m[6]);
              else row.min_bonus=-Number(m[6]);
            }
            pb.push(row);
            return;
          }
        }
        m=line.match(/(対象|相手|メインターゲット)に.*?(出血|破裂|亀裂|戦慄)があるなら.*?(基礎威力|最終威力)\s*([+＋\-−]\s*\d+)/);
        if(m){
          pb.push({ operation: "FIXED_IF_EXISTS", source: "target", param: m[2], threshold: 1, value: Number(String(m[4]).replace(/\s+/g,"").replace("−","-")), apply_to: m[3].includes("最終")?"final":"base" });
          return;
        }
        m=line.match(/(対象|相手|メインターゲット)の(出血|破裂|亀裂|戦慄)\s*(\d+)\s*につき.*?(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)(?:.*?最大(?:で)?\s*(\d+))?/);
        if(m){
          const applyTo=m[4].includes("ダイス")?"dice":(m[4].includes("最終")?"final":"base");
          const row={ operation: "PER_N_BONUS", source: "target", param: m[2], per_N: Number(m[3]), value: Number(String(m[5]).replace(/\s+/g,"").replace("−","-")), apply_to: applyTo };
          if(m[6]){
            if(row.value>=0) row.max_bonus=Number(m[6]);
            else row.min_bonus=-Number(m[6]);
          }
          pb.push(row);
          return;
        }
        m=line.match(/(対象|相手)に(出血|破裂|亀裂|戦慄)がないなら.*?(基礎威力|最終威力)\s*([+＋\-−]\s*\d+)/);
        if(m){
          pb.push({
            operation:"FIXED",
            value:Number(String(m[4]).replace(/\s+/g,"").replace("−","-")),
            apply_to:m[3].includes("最終")?"final":"base",
            condition:{ source:"target", param:m[2], operator:"EQUALS", value:0 }
          });
          return;
        }
        m=line.match(/(対象|相手)(?:の|に)(出血|破裂|亀裂|戦慄)が(\d+)以上(?:あるなら)?.*?(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)/);
        if(m){
          pb.push({
            operation:"FIXED",
            value:Number(String(m[5]).replace(/\s+/g,"").replace("−","-")),
            apply_to:m[4].includes("ダイス")?"dice":(m[4].includes("最終")?"final":"base"),
            condition:{ source:"target", param:m[2], operator:"GTE", value:Number(m[3]) }
          });
          return;
        }
        m=line.match(/(?:このラウンドの)?(自分|自身|対象|相手)の?(速度値|出血|破裂|亀裂|戦慄)が(\d+)(以上|以下|未満|より高い|より大きい|より低い|より小さい)?.*?(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)/);
        if(m){
          const opWord=_nlComparison(m[4] || "");
          pb.push({
            operation:"FIXED",
            value:Number(String(m[6]).replace(/\s+/g,"").replace("−","-")),
            apply_to:m[5].includes("ダイス")?"dice":(m[5].includes("最終")?"final":"base"),
            condition:{ source:(m[1]==="自分"||m[1]==="自身")?"self":"target", param:m[2], operator:opWord, value:Number(m[3]) }
          });
          return;
        }
        m=line.match(/速度値が(\d+)以下.*?(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)/);
        if(m){
          pb.push({
            operation:"FIXED",
            value:Number(String(m[3]).replace(/\s+/g,"").replace("−","-")),
            apply_to:m[2].includes("ダイス")?"dice":(m[2].includes("最終")?"final":"base"),
            condition:{ source:"target", param:"速度値", operator:"LTE", value:Number(m[1]) }
          });
          return;
        }
        m=line.match(/(自分|自身)に(出血|破裂|亀裂|戦慄)が(\d+)以上ないなら.*?(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)/);
        if(m){
          pb.push({
            operation:"FIXED",
            value:Number(String(m[5]).replace(/\s+/g,"").replace("−","-")),
            apply_to:m[4].includes("ダイス")?"dice":(m[4].includes("最終")?"final":"base"),
            condition:{ source:"self", param:m[2], operator:"LT", value:Number(m[3]) }
          });
          return;
        }
        m=line.match(/(自分|自身)に(出血|破裂|亀裂|戦慄)があるなら.*?(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)/);
        if(m){
          pb.push({ operation:"FIXED_IF_EXISTS", source:"self", param:m[2], threshold:1, value:Number(String(m[4]).replace(/\s+/g,"").replace("−","-")), apply_to:m[3].includes("ダイス")?"dice":(m[3].includes("最終")?"final":"base") });
          return;
        }
        m=line.match(/(自分|自身)の(出血|破裂|亀裂|戦慄)\s*(\d+)\s*につき.*?(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)(?:.*?(最大|最小)(?:で)?\s*([+\-−]?\d+))?/);
        if(m){
          const applyTo=m[4].includes("ダイス")?"dice":(m[4].includes("最終")?"final":"base");
          const row={ operation: "PER_N_BONUS", source:"self", param:m[2], per_N:Number(m[3]), value:Number(String(m[5]).replace(/\s+/g,"").replace("−","-")), apply_to:applyTo };
          if(m[7]){
            const lim=Number(String(m[7]).replace("−","-"));
            if(m[6]==="最小") row.min_bonus=lim;
            else row.max_bonus=Math.abs(lim);
          }
          pb.push(row);
          return;
        }
        m=line.match(/(自分|自身)の(蓄力|凝魔)\s*(\d+)\s*につき.*?(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)(?:.*?(最大|最小)(?:で)?\s*([+\-−]?\d+))?/);
        if(m){
          const applyTo=m[4].includes("ダイス")?"dice":(m[4].includes("最終")?"final":"base");
          const row={ operation: "PER_N_BONUS", source:"self", param:`${m[2]}_count`, per_N:Number(m[3]), value:Number(String(m[5]).replace(/\s+/g,"").replace("−","-")), apply_to:applyTo };
          if(m[7]){
            const lim=Number(String(m[7]).replace("−","-"));
            if(m[6]==="最小") row.min_bonus=lim;
            else row.max_bonus=Math.abs(lim);
          }
          pb.push(row);
          return;
        }
        m=line.match(/(自分|自身)に付与された(出血|破裂|亀裂|戦慄)\s*(\d+)\s*につき.*?(基礎威力|最終威力|ダイス威力)\s*([+＋\-−]\s*\d+)(?:.*?(最大|最小)(?:で)?\s*([+\-−]?\d+))?/);
        if(m){
          const applyTo=m[4].includes("ダイス")?"dice":(m[4].includes("最終")?"final":"base");
          const row={ operation: "PER_N_BONUS", source:"self", param:m[2], per_N:Number(m[3]), value:Number(String(m[5]).replace(/\s+/g,"").replace("−","-")), apply_to:applyTo };
          if(m[7]){
            const lim=Number(String(m[7]).replace("−","-"));
            if(m[6]==="最小") row.min_bonus=lim;
            else row.max_bonus=Math.abs(lim);
          }
          pb.push(row);
          return;
        }
        m=line.match(/(対象|相手)の(出血|破裂|亀裂|戦慄).*?威力.*?値だけ.*?(基礎威力|最終威力|ダイス威力)/);
        if(m){
          const row={ operation:"PER_N_BONUS", source:"target", param:m[2], per_N:1, value:1, apply_to:m[3].includes("ダイス")?"dice":(m[3].includes("最終")?"final":"base") };
          const max=line.match(/最大(?:で)?\s*(\d+)/);
          if(max) row.max_bonus=Number(max[1]);
          pb.push(row);
          return;
        }
        if(/自滅/.test(line)){
          tags.add("自滅");
          return;
        }
        if(/^このスキルを使用している間[、,，]\s*(?:相手|対象)の破裂威力は減少しない$/.test(line)){
          effects.push({timing:"PRE_MATCH",type:"APPLY_BUFF",target:"target",buff_id:"Bu-06",lasting:1});
          return;
        }
        if(/減少しない/.test(line)){
          return;
        }
        if(!line.trim()) return;
        _nlPushError(errors,"特記",line,"特記を解釈できません。対応文型（条件付き固定加算 / Nごと加算 / timing付き効果）で記述してください。");
      });
      return { power_bonus: pb, effects, tags: Array.from(tags) };
    }
    function _nlEffectToSeed(effect){
      const known=["timing","type","target","state_name","source","source_param","per_N","value","buff_id","buff_name","skill_id","lasting","delay","summon_template_id","repeat_count","condition"];
      const seed={};
      const extra={};
      Object.entries(effect||{}).forEach(([k,v])=>{
        if(known.includes(k)) seed[k]=v;
        else extra[k]=v;
      });
      if(effect && typeof effect==="object" && effect.data && typeof effect.data==="object"){
        const dn=String(effect.data.display_name||"").trim();
        if(dn) seed.display_name=dn;
      }
      if(Object.keys(extra).length) seed._extra_json=extra;
      return seed;
    }

    const parseList = value => String(value || '').split(',').map(row=>row.trim()).filter(Boolean);
    const number = value => value == null || value === '' || Number.isNaN(Number(value)) ? undefined : Number(value);
    function condition(value) {
      if (!value) return undefined;
      const source=String(value.source || 'self').trim(), param=_nlCleanLine(value.param || ''), operator=String(value.operator || 'GTE').trim();
      const raw=_nlCleanLine(String(value.value ?? ''));
      return source && param && operator && raw !== '' ? {source,param,operator,value:Number.isNaN(Number(raw))?raw:Number(raw)} : undefined;
    }
    // 旧入力行を経由したときの既定値・省略規則も維持する。
    function powerRow(seed) {
      const row={operation:seed.operation || 'FIXED',source:seed.source || 'self'};
      if (seed.param) row.param=_nlCleanLine(seed.param);
      if (seed.apply_to && seed.apply_to !== 'base') row.apply_to=seed.apply_to;
      for (const key of ['value','per_N','threshold','value_per_param','max_bonus','min_bonus']) {
        const value=number(seed[key] ?? (key === 'threshold' ? 1 : ''));
        if (value !== undefined) row[key]=value;
      }
      for (const key of (window.CatalogSkillTextHelp.powerRules[row.operation] || window.CatalogSkillTextHelp.powerRules.FIXED).unused) delete row[key];
      const cond=condition(seed.condition);if(cond)row.condition=cond;
      return row;
    }
    function effectRow(effect) {
      const seed=_nlEffectToSeed(effect);
      const row={timing:seed.timing || 'HIT',type:seed.type || 'APPLY_STATE',target:seed.target || 'target'};
      for (const key of ['state_name','source','source_param','buff_id','buff_name','skill_id','summon_template_id']) {
        const value=String(seed[key] || '').trim();
        if (value) row[key]=['buff_id','skill_id','summon_template_id'].includes(key)?value:_nlCleanLine(value);
      }
      if (seed.value !== undefined && seed.value !== null && String(seed.value).trim() !== '') {
        const value=row.type === 'CUSTOM_EFFECT'?_nlCleanLine(String(seed.value)):number(seed.value);
        if(value !== undefined)row.value=value;
      }
      for(const key of ['per_N','lasting','delay','repeat_count']) {const value=number(seed[key]);if(value !== undefined)row[key]=value;}
      const displayName=_nlCleanLine(String(seed.display_name || '').trim());
      if(displayName)row.data={display_name:displayName};
      const cond=condition(seed.condition);if(cond)row.condition=cond;
      if(seed._extra_json) {
        const extra=JSON.parse(JSON.stringify(seed._extra_json));
        if(extra.data && row.data)extra.data={...row.data,...extra.data};
        Object.assign(row,extra);
      }
      if(row.type === 'APPLY_BUFF' && ['Bu-11','Bu-12'].includes(String(row.buff_id || row.data?.buff_id || '').trim())) {row.lasting ??= 1;row.delay ??= 1;}
      if(row.repeat_count !== undefined && row.repeat_count <= 1)delete row.repeat_count;
      return row;
    }
    function parse(input = {}) {
      const rawCost=String(input.cost || ''), rawTrigger=String(input.trigger || ''), rawNote=String(input.note || ''), rawTags=String(input.tags || '');
      const allErrors=[];
      const splitCost=_nlSplitLines(rawCost);
      const splitTrigger=_nlSplitLines(rawTrigger);
      const splitNote=_nlSplitLines(window.CatalogSkillNotes.withoutCorrectionNote(input.category, rawNote));
      splitCost.errors.forEach(msg=>_nlPushError(allErrors,"コスト",rawCost,msg));
      splitTrigger.errors.forEach(msg=>_nlPushError(allErrors,"発動時効果",rawTrigger,msg));
      splitNote.errors.forEach(msg=>_nlPushError(allErrors,"特記",rawNote,msg));

      const costs=_nlParseCosts(splitCost.lines, allErrors);
      const triggerEffects=[];
      const triggerTags=[];
      let timing="HIT";
      for(const line of splitTrigger.lines){
        const explicit=_nlExtractTiming(line);
        if(explicit.timing) timing=explicit.timing;
        const body=explicit.body ?? line;
        const last=triggerEffects.at(-1);
        const duration=body.match(/^(\d+)\s*ラウンド継続$/);
        const max=body.match(/^\(?最大(?:で)?\s*(\d+)\)?$/);
        const reuse=body.match(/^\(?この効果による再使用は(?:\d+ラウンドに)?(\d+)(?:回|度)まで\)?$/);
        const fissureDamage=body.match(/^消費した亀裂\s*(\d+)\s*につき\s*(\d+)\s*ダメージ$/);
        const fissureBurst=body.match(/^消費した亀裂\s*(\d+)\s*につき\s*(\d+)\s*回[、,，]\s*破裂爆発$/);
        if(duration && last?.type==="APPLY_BUFF"){
          last.lasting=Number(duration[1]);
        }else if(max && last?.type==="APPLY_STATE_PER_N"){
          last.max_value=Number(max[1]);
        }else if(max && last?.type==="APPLY_BUFF_PER_N"){
          last.max_count=Number(max[1]);
        }else if(reuse && last?.type==="USE_SKILL_AGAIN"){
          last.max_reuses=Number(reuse[1]);
        }else if(fissureDamage && last?.value==="亀裂崩壊_DAMAGE"){
          last.damage_per_fissure=Math.max(1,Math.floor(Number(fissureDamage[2])/Math.max(1,Number(fissureDamage[1]))));
        }else if(fissureBurst && last?.value==="亀裂崩壊_DAMAGE"){
          delete last.damage_per_fissure;
          last.value="FISSURE_COLLAPSE";
          last.data={cost_per_trigger:Number(fissureBurst[1]),trigger_ratio:Number(fissureBurst[2]),triggered_effect:"破裂爆発"};
        }else if(/この破裂爆発は対象の破裂威力を半分にする/.test(body) && last?.value==="破裂爆発"){
          last.rupture_remainder_ratio=0.5;
        }else if(/^(?:その後[、,，]\s*)?ラウンド終了$/.test(body)){
          triggerTags.push("ラウンド終了");
        }else{
          const parsed=_nlParseTriggerLine(line, allErrors, "発動時効果", timing);
          if(parsed) triggerEffects.push(...parsed);
        }
      }
      const noteParsed=_nlParseNotes(splitNote.lines, allErrors);


      if(allErrors.length) return {rule:null,errors:allErrors};
      const tagNames={non_damage:"非ダメージ",self_target:"自己対象"};
      const tags=new Set(parseList(rawTags).map(tag=>tagNames[tag] || tag));
      triggerTags.forEach(tag=>tags.add(tag));
      (noteParsed.tags || []).forEach(tag=>tags.add(String(tag)));
      const mergedEffects=[...triggerEffects,...noteParsed.effects];
      const rule={schema:'skill_json_rule_v2'};
      const id=String(input.id || '').trim();if(id)rule.id=id;
      const cleanedTags=parseList(_nlCleanLine([...tags].join(', ')));if(cleanedTags.length)rule.tags=cleanedTags;
      let targetScope=input.target_scope ?? 'opposing_team';
      if(mergedEffects.some(effect=>effect?.type==='DAMAGE_BONUS' && effect?.condition?.source==='target' && effect?.condition?.param==='tag_ids'))targetScope='any';
      if(targetScope)rule.target_scope=targetScope;
      if(costs.length)rule.cost=costs;
      rule.power_bonus=(noteParsed.power_bonus || []).map(powerRow);
      rule.effects=mergedEffects.map(effectRow);
      return {rule,errors:[]};
    }
    return {parse};
  }
  async function copyJSON(text, clipboard) {
    if(!clipboard?.writeText) throw new Error('クリップボードを利用できません。JSON欄からコピーしてください。');
    await clipboard.writeText(text);
  }
  function renderForm(payload, tags, result, references) {
    const h = window.CatalogGlossary.escape;
    const fields = [['コスト', 'コスト'], ['発動時効果', '発動時効果'], ['特記', '特記']];
    const how = '下の3つの欄を読み取り、コスト・補正・効果を作り直します。今の設定は置き換わり、保存はしません。';
    const outcome = !result ? '<div class="cat-text-result" role="status"></div>' : result.errors.length
      ? `<div class="cat-text-result is-error" role="status"><p>読み取れない行が${result.errors.length}件あります。効果は変えていません。</p><ul class="cat-text-errors">${result.errors.map(error => `<li><strong>${h(error.column)}</strong><blockquote>${h(error.line)}</blockquote><span>${h(error.reason)}</span></li>`).join('')}</ul></div>`
      : `<div class="cat-text-result is-done" role="status"><p>効果を作りました。確かめる節：</p><div class="cat-actions"><button type="button" class="cat-button" data-section="cost">コスト</button><button type="button" class="cat-button" data-section="bonus">補正</button><button type="button" class="cat-button" data-section="effects">効果</button></div></div>`;
    return `<section class="cat-text-editor"><h3 class="cat-heading-info">文章から効果を作る${window.CatalogInfo.render('文章から効果を作る', how)}</h3>
      <div class="cat-text-run"><button type="button" class="cat-button" data-action="text-build">文章を読み取って効果を作る</button></div>${outcome}
      ${fields.map(([key, label]) => `<label class="cat-field cat-field-wide">${label}<textarea data-catalog-text data-field="${key}" rows="3">${h(payload[key] ?? '')}</textarea><span class="cat-field-error" id="cat-error-${key}"></span></label>`).join('')}
      <label class="cat-field">タグ（カンマ区切り）<input id="cat-text-tags" value="${h(tags)}"></label>
      ${window.CatalogSkillTextHelp.render(references)}</section>`;
  }
  window.CatalogSkillText={createReader,copyJSON,renderForm};
})();
