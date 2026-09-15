// The remembered theme, applied before the page is painted.
//
// This was three lines inline in the <head>, and the content security policy
// this server sends says `script-src 'self'`: the browser refused to run it, so
// the toggle worked until the next request and the choice was lost on every
// reload. The policy is right and the inline script was wrong.
//
// A file rather than a nonce, and loaded without `defer` so it still runs
// before the first paint: that is what keeps a dark-theme reader from seeing a
// white flash. It is separate from app.js, which is loaded at the end of the
// body and is where the toggle itself lives.
(function () {
  try {
    var theme = localStorage.getItem('chatlens-theme');
    if (theme === 'dark' || theme === 'light') {
      document.documentElement.setAttribute('data-theme', theme);
    }
  } catch (e) {
    // Private mode, or storage disabled. The page then follows the system
    // setting, which is the documented third state.
  }
})();
