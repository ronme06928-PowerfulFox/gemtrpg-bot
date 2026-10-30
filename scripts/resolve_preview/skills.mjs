import { readFile } from 'node:fs/promises';
import { samples } from './samples.mjs';
export { plainSkillText } from './skill_text.mjs';

export const defaultCachePath = new URL('../../data/cache/skills_cache.json', import.meta.url);

export function hydrateSamples(specs, catalog) {
  return specs.map(spec => ({ ...spec,
    skills: Object.fromEntries(['attacker', 'defender'].map(side => {
      const id = spec.skillIds[side];
      if (!id) return [side, null];
      const skill = catalog[id];
      if (!skill || skill['スキルID'] !== id) throw new Error(`スキルID「${id}」がキャッシュにありません（${spec.label}）。`);
      return [side, { id: skill['スキルID'], name: spec.nameOverrides?.[side] || skill['デフォルト名称'],
        attribute: skill['属性'],
        fields: ['使用時効果', '発動時効果', '特記'].filter(label => skill[label]?.trim())
          .map(label => ({ label, text: skill[label] })),
      }];
    })),
  }));
}

export async function loadSamples(cachePath = defaultCachePath) {
  let text;
  try {
    text = await readFile(cachePath, 'utf8');
  } catch (error) {
    if (error.code === 'ENOENT') throw new Error(`スキルキャッシュが見つかりません: ${cachePath}。data/cache/skills_cache.json を用意してから組み立ててください。`);
    throw error;
  }
  let catalog;
  try { catalog = JSON.parse(text); }
  catch { throw new Error(`スキルキャッシュのJSONが壊れています: ${cachePath}`); }
  return hydrateSamples(samples, catalog);
}
