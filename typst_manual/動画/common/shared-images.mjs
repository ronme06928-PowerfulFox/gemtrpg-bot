// 画像URLは共有CSSで一度だけ定義する。場面の切替では参照を変更しない。
export const videoImages = {
  ruins: { source: 'ruins-battle.png', file: 'ruins.webp' },
  ally: { source: 'ally-adventurer.png', file: 'ally.webp' },
  enemy: { source: 'wolf-shularker.png', file: 'enemy.webp' },
  logo: { source: 'gemuria_logo.png', file: 'gemuria_logo.png' }
};

export function sharedImageCss(assets) {
  return ':root {\n' + Object.entries(assets).map(([key, file]) => `  --video-image-${key}: url("${file}");`).join('\n') + '\n}\n'
    + Object.keys(assets).map((key) => `[data-video-image="${key}"] { background-image: var(--video-image-${key}); }`).join('\n') + '\n';
}

export function shareSceneImages(html) {
  return html.replace(/<img\b[^>]*>/g, (tag) => {
    const src = tag.match(/src="([^"]+)"/)?.[1];
    const entry = Object.entries(videoImages).find(([, image]) => src === `images/${image.source}`);
    if (!entry) return tag;
    const className = tag.match(/class="([^"]*)"/)?.[1];
    const alt = tag.match(/alt="([^"]*)"/)?.[1] || '';
    return `<div class="${className ? className + ' ' : ''}video-shared-image" data-video-image="${entry[0]}" role="img" aria-label="${alt}"></div>`;
  });
}
