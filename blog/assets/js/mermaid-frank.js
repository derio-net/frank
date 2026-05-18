/* Mermaid initializer for The Frank Papers series.
   Loaded only on pages with series: papers in frontmatter (see head-end.html). */
(function () {
  var script = document.createElement('script');
  script.src = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js';
  script.onload = function () {
    mermaid.initialize({
      startOnLoad: true,
      theme: 'base',
      themeVariables: {
        background: '#0d1117',
        primaryColor: '#1e3a5f',
        primaryTextColor: '#e6edf3',
        primaryBorderColor: '#1f6feb',
        lineColor: '#30a46c',
        secondaryColor: '#161b22',
        tertiaryColor: '#21262d',
        edgeLabelBackground: '#0d1117',
        clusterBkg: '#161b22',
        titleColor: '#e6edf3',
        fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace',
        fontSize: '14px',
      },
    });
  };
  document.head.appendChild(script);
})();
