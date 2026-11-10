(function () {
  // JSONの2と2.0はPythonの要約では区別される。APIで届いた数値の表記を編集・保存にも引き継ぐ。
  const literals = new WeakMap();
  function parse(text) {
    return JSON.parse(text,function(key,value,context) {
      if (typeof value === 'number' && context?.source && /[.eE]/.test(context.source)) {
        if (!literals.has(this)) literals.set(this,new Map());
        literals.get(this).set(key,context.source);
      }
      return value;
    });
  }
  function stringify(value,space = 2) {
    return JSON.stringify(value,function(key,child) {
      const raw = literals.get(this)?.get(key);
      return raw !== undefined && Object.is(child,Number(raw)) ? JSON.rawJSON(raw) : child;
    },space);
  }
  const clone = value => parse(stringify(value));
  function numberText(holder,key) {
    const raw = holder && literals.get(holder)?.get(key);
    if (raw === undefined || !Object.is(holder[key],Number(raw))) return null;
    return Number.isInteger(holder[key]) ? `${holder[key]}.0` : String(holder[key]);
  }
  function ordered(value,keys) {
    const result = Object.fromEntries(keys.map(key=>[key,value[key]]));
    if (literals.has(value)) literals.set(result,new Map(literals.get(value)));
    return result;
  }
  function forget(holder,key) { literals.get(holder)?.delete(key); }
  window.CatalogJson = {parse,stringify,clone,numberText,ordered,forget};
})();
