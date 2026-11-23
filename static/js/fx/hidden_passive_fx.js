(function () {
  function cover(breaking = false) {
    if (breaking) return '<span class="hidden-passive-cover is-breaking" aria-hidden="true"></span>';
    return '<div class="hidden-passive-cover" aria-label="伏せたパッシブ">？？？</div>';
  }

  function newThisRound(character, state) {
    return Number(state?.round) > 0 && !state.is_round_ended
      && Number(character?.passive_revealed_round) === Number(state.round);
  }

  window.HiddenPassiveFx = { cover, newThisRound };
})();
