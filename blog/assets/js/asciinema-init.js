/* asciinema player bootstrap.
 *
 * The {{< asciinema >}} shortcode used to emit a per-instance inline <script>
 * calling AsciinemaPlayer.create(). blog.derio.net serves `script-src 'self'`
 * with no 'unsafe-inline', so every such block would be dropped and the player
 * would never appear. The shortcode now emits configuration as data-* attributes
 * and this external script consumes them.
 *
 * NOTE: the player library itself is still loaded from unpkg.com by
 * custom/head-end.html, which the CSP also blocks. Vendor it into
 * blog/assets/ (or widen the CSP) before using the shortcode — see the comment
 * there. scripts/check_blog_build.py fails the build if an off-origin asset is
 * ever emitted, so this cannot ship silently broken.
 */
(function () {
  "use strict";

  function num(value, fallback) {
    var n = parseFloat(value);
    return isNaN(n) ? fallback : n;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var containers = document.querySelectorAll(".asciinema-container[data-cast-src]");
    if (!containers.length || typeof window.AsciinemaPlayer === "undefined") return;

    var theme = document.documentElement.classList.contains("dark")
      ? "asciinema"
      : "solarized-light";

    containers.forEach(function (el) {
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
  });
})();
