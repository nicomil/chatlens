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

// I preset sono la scelta principale: impostano le opzioni di dettaglio, che
// restano visibili e modificabili per chi deve scostarsene.
(function () {
  var PRESETS = {
    base:        { llm: false, topics: false },
    validazione: { llm: true,  topics: false },
    completa:    { llm: true,  topics: true }
  };

  var form = document.getElementById('launch');
  if (!form) { return; }

  function apply(name) {
    var preset = PRESETS[name];
    if (!preset) { return; }
    Object.keys(preset).forEach(function (field) {
      var box = form.querySelector('input[name="' + field + '"]');
      if (box) { box.checked = preset[field]; }
    });
    form.querySelectorAll('.preset').forEach(function (card) {
      card.classList.toggle('on', card.querySelector('input').checked);
    });
    // Un solo evento, sul form: la stima lo ascolta. Il run parte soltanto
    // dall'invio del modulo, mai da un cambiamento.
    form.dispatchEvent(new Event('change', { bubbles: true }));
  }

  form.addEventListener('change', function (event) {
    if (event.target.name === 'preset') {
      apply(event.target.value);
      return;
    }
    // Toccando le caselle di dettaglio la scelta non corrisponde piu' a nessun
    // preset: si toglie l'evidenziazione invece di lasciarla mentire.
    if (event.target.name === 'llm' || event.target.name === 'topics') {
      var stato = {
        llm: form.querySelector('input[name="llm"]').checked,
        topics: form.querySelector('input[name="topics"]').checked
      };
      var match = Object.keys(PRESETS).find(function (k) {
        return PRESETS[k].llm === stato.llm && PRESETS[k].topics === stato.topics;
      });
      form.querySelectorAll('.preset').forEach(function (card) {
        var input = card.querySelector('input');
        input.checked = input.value === match;
        card.classList.toggle('on', input.checked);
      });
    }
  });
})();
