/* asciinema player bootstrap.
 *
 * The {{< asciinema >}} shortcode used to emit a per-instance inline <script>
 * calling AsciinemaPlayer.create(). A blog serving `script-src 'self'` with no
 * 'unsafe-inline' drops every such block, so the player never appeared — with no
 * build error and nothing an author would think to look for. The shortcode now
 * emits its configuration as data-* attributes and this external script consumes
 * them.
 *
 * The player library itself is vendored at assets/vendor/asciinema-player/ and
 * served same-origin, so the whole feature works under `script-src 'self'` with
 * no CSP exemption and no third party in the request path.
 */
(function () {
  "use strict";

  function num(value, fallback) {
    var n = parseFloat(value);
    return isNaN(n) ? fallback : n;
  }

  function init() {
    var containers = document.querySelectorAll(".asciinema-container[data-cast-src]");
    if (!containers.length || typeof window.AsciinemaPlayer === "undefined") return;

    var theme = document.documentElement.classList.contains("dark")
      ? "asciinema"
      : "solarized-light";

    Array.prototype.forEach.call(containers, function (el) {
      window.AsciinemaPlayer.create(el.dataset.castSrc, el, {
        cols: num(el.dataset.cols, 120),
        rows: num(el.dataset.rows, 30),
        speed: num(el.dataset.speed, 1),
        idleTimeLimit: num(el.dataset.idleTimeLimit, 2),
        poster: el.dataset.poster || "npt:0:3",
        theme: theme,
        fit: "width",
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
