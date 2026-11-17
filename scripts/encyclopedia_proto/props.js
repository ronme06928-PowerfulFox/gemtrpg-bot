// 棚の空きに置く小物。真鍮色の影絵で描き、本より目立たせない。飾りなので読み上げない。
// 塗りは currentColor（CSS の真鍮色）、面の区切りは暗い線、光は細い明るい線だけにする。
const edge = 'stroke="#1b1321" stroke-opacity=".55" stroke-width="1" fill="none"';
const shine = 'stroke="#fff0d2" stroke-opacity=".45" stroke-width="1" fill="none" stroke-linecap="round"';

const PROP_ART = {
  hourglass: `<svg viewBox="0 0 56 96" class="prop prop-hourglass">
    <path fill="currentColor" d="M6 4h44v6H6zM6 86h44v6H6zM9 10h3v76H9zM44 10h3v76h-3z"/>
    <path fill="currentColor" fill-opacity=".28" d="M15 10h26c0 17-10 22-10 38s10 21 10 38H15c0-17 10-22 10-38S15 27 15 10z"/>
    <path fill="currentColor" class="sand-top" d="M19 18h18c-2 8-7 12-9 18-2-6-7-10-9-18z"/>
    <path fill="currentColor" class="sand-fall" d="M27.5 47h1v24h-1z"/>
    <path fill="currentColor" d="M18 86c1-8 6-11 10-11s9 3 10 11z"/>
    <path ${shine} d="M18 13c1 9 5 14 7 19M18 83c1-6 3-10 6-13"/>
    <path ${edge} d="M6 10h44M6 86h44"/>
  </svg>`,
  dice: `<svg viewBox="0 0 52 56" class="prop prop-dice">
    <path fill="currentColor" d="M26 3l21 12v26L26 53 5 41V15z"/>
    <path ${edge} d="M26 3v13M5 15l21 1 21-1M26 16l-12 22h24zM14 38L5 41M38 38l9 3M14 38l12 15 12-15"/>
    <path ${shine} d="M8 17l16 0.8M26 5v9"/>
  </svg>`,
  candle: `<svg viewBox="0 0 44 100" class="prop prop-candle">
    <g class="flame">
      <ellipse cx="22" cy="16" rx="10" ry="13" fill="#ffd38a" fill-opacity=".14"/>
      <path d="M22 5c4 6 5 9 5 12a5 5 0 0 1-10 0c0-3 1-6 5-12z" fill="#ffd38a" fill-opacity=".85"/>
    </g>
    <path fill="currentColor" fill-opacity=".55" d="M17 27h10v32H17z"/>
    <path fill="currentColor" d="M21.4 22h1.2v6h-1.2zM9 59h26l-4 5H13zM19.5 64h5v22h-5zM10 92c2-4 7-6 12-6s10 2 12 6v3H10z"/>
    <path ${shine} d="M19 30v26M12 61h18M14 90c2-2 5-3 8-3"/>
  </svg>`,
  quill: `<svg viewBox="0 0 64 100" class="prop prop-quill">
    <path fill="currentColor" fill-opacity=".7" d="M46 3c13 8 16 25 3 42L31 76l-3-2 16-33C53 25 51 12 46 3z"/>
    <path ${edge} d="M46 3c3 15 0 27-9 40L29 75"/>
    <path fill="currentColor" d="M12 70h34l-3 25H15zM10 66h38v5H10z"/>
    <path ${shine} d="M16 74l2 18M12 67h33"/>
    <path ${edge} d="M10 71h38"/>
  </svg>`,
};

const PROP_KEYS = new Set(Object.keys(PROP_ART));
const propArt = key => `<span class="shelf-prop" aria-hidden="true">${PROP_ART[key]}</span>`;
