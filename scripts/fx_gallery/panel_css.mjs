// 本番の解決パネルのCSSを一覧へ取り込む。本番のファイルは書き換えない（計画56 §4.1a）。
export const GALLERY_PANEL_SELECTOR = '[data-gallery-resolve-panel]';
const PANEL_ID = '#resolve-flow-panel';

// 上の階層の規則と @media を順に取り出す。コメントは捨てる。
function blocks(css) {
  const source = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const result = [];
  let depth = 0, start = 0, head = 0;
  for (let i = 0; i < source.length; i++) {
    if (source[i] === '{') {
      if (depth === 0) head = i;
      depth++;
    } else if (source[i] === '}') {
      depth--;
      if (depth === 0) {
        result.push({ prelude: source.slice(start, head).trim(), body: source.slice(head + 1, i) });
        start = i + 1;
      }
    }
  }
  return result;
}

// `#resolve-flow-panel` を含む規則だけを残し、ID を一覧の属性に付け替える。
export function extractResolvePanelCss(css) {
  const out = [];
  for (const { prelude, body } of blocks(css)) {
    if (prelude.startsWith('@media')) {
      const inner = extractResolvePanelCss(body);
      if (inner) out.push(`${prelude} {\n${inner}\n}`);
    } else if (prelude.includes(PANEL_ID)) {
      out.push(`${prelude.split(PANEL_ID).join(GALLERY_PANEL_SELECTOR)} {${body}}`);
    }
  }
  return out.join('\n');
}
