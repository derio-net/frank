(function () {
  'use strict';

  var STORAGE_KEY = 'frank-read-posts';

  function getReadPosts() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
    } catch (e) {
      return [];
    }
  }

  function markCurrentAsRead() {
    var path = window.location.pathname;
    var readPosts = getReadPosts();
    if (readPosts.indexOf(path) === -1) {
      readPosts.push(path);
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(readPosts));
      } catch (e) {
        // localStorage full or unavailable
      }
    }
  }

  function markSidebarLinks() {
    var readPosts = getReadPosts();
    if (readPosts.length === 0) return;

    var links = document.querySelectorAll('.hextra-sidebar-container a[href]');
    links.forEach(function (link) {
      var href = link.getAttribute('href');
      var normalizedHref = href.endsWith('/') ? href : href + '/';
      var isRead = readPosts.some(function (p) {
        var normalizedP = p.endsWith('/') ? p : p + '/';
        return normalizedP === normalizedHref;
      });
      if (isRead && !link.querySelector('.read-marker')) {
        var marker = document.createElement('span');
        marker.className = 'read-marker';
        marker.textContent = '\u2713';
        marker.title = 'Read';
        link.appendChild(marker);
      }
    });
  }

  if (window.location.pathname.indexOf('/docs/') !== -1 ||
      window.location.pathname.indexOf('/frank/docs/') !== -1) {
    markCurrentAsRead();
  }

  /* The "clear read history" footer link. This handler was an inline <script>
     in custom/footer.html until a blog turned on `script-src 'self'`, which
     dropped it silently — the link rendered and did nothing. It lives here
     rather than in a second asset because it is the same feature and needs the
     same STORAGE_KEY, and head-end.html already loads this file on every page. */
  function bindClearLink() {
    var link = document.getElementById('clear-read-history');
    if (!link) return;
    link.addEventListener('click', function (e) {
      e.preventDefault();
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch (err) {
        /* localStorage unavailable (private mode, disabled) — nothing to clear */
      }
      window.location.reload();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      markSidebarLinks();
      bindClearLink();
    });
  } else {
    markSidebarLinks();
    bindClearLink();
  }
})();
