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
