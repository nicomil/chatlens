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

// The presets are the main choice, and now the only one: the server reads the
// preset field itself, so this only keeps the cards looking like what is
// selected. It used to copy the choice onto two checkboxes, which is what made
// the cards work at all — with this file blocked, every preset started the same
// free run.
(function () {
  var form = document.getElementById('launch');
  if (!form) { return; }

  form.addEventListener('change', function (event) {
    if (event.target.name !== 'preset') { return; }
    form.querySelectorAll('.preset').forEach(function (card) {
      card.classList.toggle('on', card.querySelector('input').checked);
    });
    // A single event, on the form: the estimate listens for it. The run starts
    // only from the form submission, never from a change.
    form.dispatchEvent(new Event('change', { bubbles: true }));
  });
})();

// The theme. Three states rather than two: the toggle switches between light
// and dark, and until it is used the page follows the system. The choice is
// remembered in this browser only — there is nothing on the server to keep it
// in, and it is a preference about a screen, not about the data.
(function () {
  var button = document.getElementById('themetoggle');
  if (!button) { return; }

  function current() {
    var set = document.documentElement.getAttribute('data-theme');
    if (set) { return set; }
    return window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark' : 'light';
  }

  button.addEventListener('click', function () {
    var next = current() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('chatlens-theme', next); } catch (e) { /* private mode */ }
  });
})();
