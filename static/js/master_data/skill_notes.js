(function () {
  const sentences = /(?:\[\[[^\]\n]+\]\]|[^。\n])+。?/g;
  function matches(category, sentence) {
    if (!Object.hasOwn(catalogNoCorrectionNotes, category)) return false;
    const plain = sentence.replace(/\[\[[^|\]\n]+\|([^\]\n]+)\]\]/g, '$1').trim();
    return plain.replace(/。$/, '') === catalogNoCorrectionNotes[category].replace(/。$/, '');
  }
  function omitsCorrection(category, notes) {
    return typeof notes === 'string' && (notes.match(sentences) || []).some(sentence => matches(category, sentence));
  }
  function withoutCorrectionNote(category, notes) {
    return notes.replace(sentences, sentence => matches(category, sentence) ? '' : sentence);
  }
  window.CatalogSkillNotes = {omitsCorrection, withoutCorrectionNote};
})();
