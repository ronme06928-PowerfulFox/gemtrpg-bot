// CSSの共有画像も、imgと同じくデコード完了を確かめる。
export async function waitForVideoImages(page) {
  return page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([...document.images].map((e) => e.decode()));
    const images = new Map();
    for (const element of document.querySelectorAll('[data-video-image]')) {
      const background = getComputedStyle(element).backgroundImage;
      const src = background.match(/^url\(["']?(.*?)["']?\)$/)?.[1];
      if (!src) throw new Error(`共有画像がない: ${element.dataset.videoImage}`);
      if (!images.has(src)) {
        const image = new Image(); image.src = src;
        images.set(src, image.decode().then(() => {
          if (!image.naturalWidth) throw new Error('共有画像をデコードできない');
          return { width: image.naturalWidth, height: image.naturalHeight };
        }));
      }
    }
    return Promise.all(images.values());
  });
}
