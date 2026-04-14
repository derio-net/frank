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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', markSidebarLinks);
  } else {
    markSidebarLinks();
  }
})();
