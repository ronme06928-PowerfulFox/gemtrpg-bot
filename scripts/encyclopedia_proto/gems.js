const jewels = {
  ruby:     { hue: '#f6a1b1', light: '#ffd7de', mid: '#ba345e', dark: '#480f29', cut: 'oval' },
  sapphire: { hue: '#a8c3ff', light: '#d9e9ff', mid: '#376dce', dark: '#142854', cut: 'emerald' },
  emerald:  { hue: '#95e3cb', light: '#caffeb', mid: '#298c77', dark: '#093e34', cut: 'emerald' },
  amethyst: { hue: '#d4b0ff', light: '#eee0ff', mid: '#8f50bd', dark: '#3c1758', cut: 'kite' },
  topaz:    { hue: '#f5b37b', light: '#fff0be', mid: '#c47c42', dark: '#552f1b', cut: 'cushion' },
  pearl:    { hue: '#f3ecdd', light: '#fff9f2', mid: '#af9da6', dark: '#4b424b', cut: 'oval' },
  prism:    { hue: '#f8e5ff', light: '#fcf8ff', mid: '#a28fae', dark: '#47354d', cut: 'kite' },
  citrine:  { hue: '#f2ed7d', light: '#ffffcd', mid: '#b6a423', dark: '#534716', cut: 'marquise' },
  aquamarine: { hue: '#91e9f1', light: '#e7ffff', mid: '#389cae', dark: '#163e51', cut: 'marquise' },
  lapis:    { hue: '#a0a3fa', light: '#e9dcff', mid: '#5655a5', dark: '#25234d', cut: 'shield' },
  garnet:   { hue: '#e38c93', light: '#ffcacf', mid: '#963f49', dark: '#44141c', cut: 'shield' },
  moonstone: { hue: '#deebf6', light: '#edf8ff', mid: '#94aaba', dark: '#394957', cut: 'cushion' },
  peridot:  { hue: '#c4e383', light: '#f1ffc9', mid: '#769435', dark: '#35451a', cut: 'shield' },
  onyx:     { hue: '#bcb7c5', light: '#e5dce4', mid: '#57515d', dark: '#19161b', cut: 'emerald' },
  tourmaline: { hue: '#f4aad7', light: '#ffe3f5', mid: '#a64e83', dark: '#4a1d3d', cut: 'marquise' },
  spinel:   { hue: '#c6aee6', light: '#f2e2ff', mid: '#786384', dark: '#3a2b49', cut: 'cushion' },
};
const cuts = {
  oval: [[50,5],[75,16],[91,42],[83,73],[50,94],[17,73],[9,42],[25,16]],
  emerald: [[25,10],[75,10],[91,26],[91,72],[75,89],[25,89],[9,72],[9,26]],
  kite: [[50,3],[76,20],[91,45],[72,70],[50,95],[28,70],[9,45],[24,20]],
  cushion: [[27,10],[73,10],[91,29],[91,69],[73,89],[27,89],[9,69],[9,29]],
  marquise: [[50,3],[68,20],[79,48],[70,73],[50,96],[30,73],[21,48],[32,20]],
  shield: [[33,11],[67,11],[88,24],[82,57],[63,86],[50,95],[37,86],[12,24]],
};
const points = vertices => vertices.map(vertex => vertex.join(',')).join(' ');
const spectrum = ['#eb638f', '#ffb166', '#f6df79', '#6edbb5', '#73a9ff', '#b48aea'];

function jewelDefinitions() {
  return `<svg class="gem-definitions" aria-hidden="true" xmlns="http://www.w3.org/2000/svg"><defs>${Object.entries(jewels).map(([key, gem]) => {
    const outline = cuts[gem.cut];
    const table = outline.map(([x,y]) => [50 + (x - 50) * .48, 47 + (y - 50) * .47]);
    const palette = [
      ['0%','#fffaf1'], ['22%',gem.light], ['66%',gem.mid], ['100%',gem.dark],
    ];
    const gradients = [0, 72, 141, 222, 286].map((angle, index) => {
      const dispersed = [['0%', '#fff', .35], ['32%', spectrum[index], .86],
        ['62%', spectrum[index + 1], .73], ['84%', '#f8fbff', .44], ['100%', '#fff', .9]];
      const stops = key === 'prism' ? dispersed : index % 2 ? [palette[0], palette[2], ['82%',gem.dark], ['100%',gem.light]] : palette;
      return `<linearGradient id="${key}-facet-${index}" gradientTransform="rotate(${angle} .5 .5)">${stops.map(([offset,color,opacity = 1]) => `<stop offset="${offset}" stop-color="${color}" stop-opacity="${opacity}"/>`).join('')}</linearGradient>`;
    }).join('');
    const faces = outline.map((vertex, i) => {
      const j = (i + 1) % outline.length;
      return `<polygon points="${points([vertex,outline[j],table[i]])}" fill="url(#${key}-facet-${i % 5})"/>
        <polygon points="${points([outline[j],table[j],table[i]])}" fill="url(#${key}-facet-${(i + 3) % 5})"/>`;
    }).join('');
    return `${gradients}<radialGradient id="${key}-light" cx="43%" cy="34%" r="72%">
      <stop stop-color="white" stop-opacity=".93"/><stop offset=".3" stop-color="${gem.light}" stop-opacity=".42"/>
      <stop offset=".77" stop-color="${gem.mid}" stop-opacity=".15"/><stop offset="1" stop-color="${gem.dark}" stop-opacity="${key === 'prism' ? '.19' : '.62'}"/>
      </radialGradient><symbol id="${key}-cut" viewBox="0 0 100 100">
        <polygon points="${points(outline)}" fill="${key === 'prism' ? '#f8fbff' : gem.dark}" fill-opacity="${key === 'prism' ? '.18' : '1'}" stroke="${gem.hue}" stroke-width="1.4"/>
        <g stroke="${gem.light}" stroke-opacity=".33" stroke-width=".55">${faces}</g>
        <polygon points="${points(table)}" fill="url(#${key}-facet-3)" stroke="${gem.light}" stroke-opacity=".5"/>
        <polygon points="${points(outline)}" fill="url(#${key}-light)"/>
        <path d="M${outline[0].join(' ')}L${outline[7].join(' ')}L${outline[6].join(' ')}" fill="none" stroke="white" stroke-opacity=".82" stroke-width="1.35"/>
        <path d="M${table[0].join(' ')}L${table[1].join(' ')}" stroke="white" stroke-opacity=".72" stroke-width=".9"/>
        </symbol>`;
  }).join('')}</defs></svg>`;
}

function jewelArt(color, moving = false) {
  return `<svg class="gem${moving ? ' gem-motion' : ''}" viewBox="0 0 100 100" aria-hidden="true"><use href="#${color}-cut"/>
    ${moving ? '<path class="spark" d="M24 11l2 8 8 2-8 2-2 8-2-8-8-2 8-2z"/><path class="spark second" d="M76 64l1 5 5 1-5 1-1 5-1-5-5-1 5-1z"/>' : ''}</svg>`;
}
