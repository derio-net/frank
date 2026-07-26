/* Mermaid initialisation — external replacement for Hextra's inline init.
 *
 * The theme's `_partials/scripts/mermaid.html` ends in an inline <script> that
 * calls mermaid.initialize() and installs a MutationObserver to re-render on
 * dark/light toggle. blog.derio.net serves `script-src 'self'` with no
 * 'unsafe-inline', so that block is dropped by the browser. Diagrams still
 * appeared — mermaid.js self-starts — but always in the light theme, and they
 * stopped following the theme toggle across all 80 posts that use mermaid.
 *
 * Rather than fork the theme partial (whose loader does a build-time remote
 * fetch we do not want to duplicate), this file re-implements the same two
 * behaviours from an external asset. The theme's inline block stays in the
 * markup, inert; this one does the work.
 *
 * Load order matters: head-end.html loads this with `defer`, and the theme's
 * mermaid.min.js is also deferred but later in the document. Deferred scripts
 * run in document order, all before DOMContentLoaded — so registering on
 * DOMContentLoaded guarantees window.mermaid exists by the time we run.
 */
(function () {
  "use strict";

  function currentTheme() {
    return document.documentElement.classList.contains("dark") ? "dark" : "default";
  }

  document.addEventListener("DOMContentLoaded", function () {
    var nodes = document.querySelectorAll(".mermaid");
    if (!nodes.length || typeof window.mermaid === "undefined") return;

    // Keep the original source: re-rendering needs the markup, not the SVG
    // mermaid replaced it with. This round-trips the page's OWN build-time
    // content through dataset and back — there is no user-supplied input in
    // this path, and it mirrors upstream Hextra's behaviour exactly.
    nodes.forEach(function (el) {
      el.dataset.original = el.innerHTML;
    });

    window.mermaid.initialize({ startOnLoad: true, theme: currentTheme() });

    var timeout;
    new MutationObserver(function () {
      clearTimeout(timeout);
      timeout = setTimeout(function () {
        document.querySelectorAll(".mermaid").forEach(function (el) {
          el.innerHTML = el.dataset.original;
          el.removeAttribute("data-processed");
        });
        window.mermaid.initialize({ startOnLoad: true, theme: currentTheme() });
        window.mermaid.init();
      }, 150);
    }).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
  });
})();
