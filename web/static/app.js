// Il log resta agganciato in fondo mentre avanza, ma solo finche' non lo si
// scorre a mano: se si sta leggendo piu' in alto, l'aggiornamento automatico
// non deve strappare via la posizione.
(function () {
  var wrap = document.getElementById('logwrap');
  if (!wrap) { return; }
  var pinned = true;

  wrap.addEventListener('scroll', function () {
    pinned = wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight < 40;
  });

  document.body.addEventListener('htmx:afterSwap', function () {
    if (pinned) { wrap.scrollTop = wrap.scrollHeight; }
  });
})();

// I preset compilano il modulo al posto dell'utente: quasi sempre si vuole uno
// scenario, non una combinazione di opzioni. Le opzioni restano lì sotto per
// chi ha bisogno di scostarsene.
(function () {
  var PRESETS = {
    base:        { llm: false, topics: false },
    validazione: { llm: true,  topics: false },
    completa:    { llm: true,  topics: true }
  };

  function apply(name) {
    var preset = PRESETS[name];
    if (!preset) { return; }
    ['llm', 'topics'].forEach(function (field) {
      var box = document.querySelector('input[name="' + field + '"]');
      if (!box) { return; }
      box.checked = preset[field];
      // Aprire la sezione scelta e chiudere l'altra rende visibile cosa
      // comporta il preset, invece di limitarsi a spuntare una casella.
      var section = box.closest('details');
      if (section) { section.open = preset[field]; }
    });
    document.querySelectorAll('.preset').forEach(function (b) {
      b.classList.toggle('on', b.dataset.preset === name);
    });
    // La stima si aggiorna da sola: htmx ascolta i cambiamenti del modulo.
    htmx.trigger('#launch', 'change');
  }

  document.body.addEventListener('click', function (event) {
    var button = event.target.closest('.preset');
    if (button) { apply(button.dataset.preset); }
  });
})();
