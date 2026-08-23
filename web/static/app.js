// The log stays pinned to the bottom as it grows, but only until it is
// scrolled by hand: if the reader is looking further up, the automatic update
// must not tear the position away.
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

// The presets are the main choice: they set the detail options, which stay
// visible and editable for anyone who needs to depart from them.
(function () {
  var PRESETS = {
    base:       { llm: false, topics: false },
    validation: { llm: true,  topics: false },
    full:       { llm: true,  topics: true }
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
    // A single event, on the form: the estimate listens for it. The run starts
    // only from the form submission, never from a change.
    form.dispatchEvent(new Event('change', { bubbles: true }));
  }

  form.addEventListener('change', function (event) {
    if (event.target.name === 'preset') {
      apply(event.target.value);
      return;
    }
    // Touching the detail boxes means the choice no longer matches any preset:
    // the highlight is removed rather than left to lie.
    if (event.target.name === 'llm' || event.target.name === 'topics') {
      var state = {
        llm: form.querySelector('input[name="llm"]').checked,
        topics: form.querySelector('input[name="topics"]').checked
      };
      var match = Object.keys(PRESETS).find(function (k) {
        return PRESETS[k].llm === state.llm && PRESETS[k].topics === state.topics;
      });
      form.querySelectorAll('.preset').forEach(function (card) {
        var input = card.querySelector('input');
        input.checked = input.value === match;
        card.classList.toggle('on', input.checked);
      });
    }
  });
})();
