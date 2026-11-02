import { pickStageLayout, fitStage } from './layout.mjs';

// 計画58 §5.3：ブラウザの中の大きさと、その時の地図の欄の幅（ローカルのアプリで実測）。
export const SCREENS = Object.freeze([
  { id: '1920x945', label: '1920×945（FHD 100%）', width: 1920, height: 945, map: 1448 },
  { id: '1536x730', label: '1536×730（FHD 125%）', width: 1536, height: 730, map: 1071 },
  { id: '1440x780', label: '1440×780', width: 1440, height: 780, map: 977 },
  { id: '1366x650', label: '1366×650（1366×768のノート）', width: 1366, height: 650, map: 905 },
  { id: '1280x600', label: '1280×600（FHD 150%）', width: 1280, height: 600, map: 821 },
  { id: '1100x650', label: '1100×650', width: 1100, height: 650, map: 644 },
  { id: '980x650', label: '980×650', width: 980, height: 650, map: 527 },
]);

// 本番と同じ決め方：地図の欄の幅×0.92と画面の高さで組を選び、同じ fitStage で縮める。
export function fitScreen(screen) {
  const available = screen.map * 0.92;
  const layout = pickStageLayout(available, screen.height);
  return { layout, fit: fitStage(layout, available, screen.height) };
}
