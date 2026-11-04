import test from 'node:test';
import assert from 'node:assert/strict';
import { shareSceneImages, sharedImageCss } from '../common/shared-images.mjs';

test('11場面で使う画像URLは共有CSSに1つずつだけ置く', () => {
  const assets = { ruins: 'images/ruins.webp', ally: 'images/ally.webp' };
  const css = sharedImageCss(assets);
  const original = '<img src="images/ruins-battle.png" alt="遺跡"><img class="app-portrait" src="images/ally-adventurer.png" alt="男冒険者">';
  const scene = shareSceneImages(original);
  assert.equal((css.match(/url\(/g) || []).length, 2);
  assert.ok(!scene.includes('src='));
  assert.ok(!scene.repeat(11).includes('url('));
  assert.match(scene, /role="img" aria-label="遺跡"/);
  assert.match(scene, /class="app-portrait video-shared-image"/);
  assert.match(scene, /data-video-image="ally"/);
});

test('未登録の画像は元のimgのまま保つ', () => {
  const original = '<img src="images/other.png" alt="別の画像">';
  assert.equal(shareSceneImages(original), original);
});

test('冒頭とクレジットの未加工ロゴも1つのURLを共有する', () => {
  assert.match(shareSceneImages('<img class="credits-logo" src="images/gemuria_logo.png" alt="ロゴ">'), /data-video-image="logo"/);
});
