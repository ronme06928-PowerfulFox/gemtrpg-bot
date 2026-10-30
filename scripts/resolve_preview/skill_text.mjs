export function plainSkillText(text) {
  return String(text).replace(/\[\[[^|\]]+\|([^\]]+)\]\]/g, '$1');
}
