/* "Clear read history" footer link.
 *
 * Was an inline <script> in layouts/partials/custom/footer.html until
 * blog.derio.net gained `script-src 'self'` (no 'unsafe-inline'), which dropped
 * it on every page — the link rendered but did nothing. Externalised so the
 * browser will actually run it.
 *
 * The link is emitted on every page, so guard on its presence rather than
 * assuming it.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var link = document.getElementById("clear-read-history");
    if (!link) return;

    link.addEventListener("click", function (e) {
      e.preventDefault();
      localStorage.removeItem("frank-read-posts");
      window.location.reload();
    });
  });
})();
