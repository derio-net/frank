#!/usr/bin/env python3
"""Check the public reader contract after blog/scripts/build-site.py."""
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse


def check(public):
    catalog = json.loads((public / 'content-index.json').read_text(encoding='utf-8'))
    base = 'https://blog.derio.net/frank/'
    assert catalog['site'] == base, 'catalog canonical URL drifted'
    assert catalog['schema_version'] == 1
    assert catalog['articles'], 'empty catalog'
    assert 'content-index.json' in (public / 'llms.txt').read_text(encoding='utf-8')
    assert ET.parse(public / 'index.xml').findall('./channel/item'), 'empty RSS feed'
    markdown_paths = set()
    for article in catalog['articles']:
        url = article['url']
        assert url.startswith(base), f'noncanonical URL: {url}'
        relative = unquote(urlparse(url).path).removeprefix('/frank/')
        directory = (public / relative).resolve()
        assert directory.is_relative_to(public), f'path outside public: {relative}'
        html = (directory / 'index.html').read_text(encoding='utf-8')
        path = directory / 'index.md'
        markdown_paths.add(path)
        data = path.read_bytes()
        assert article['markdown_url'] == url + 'index.md'
        assert article['content_sha256'] == hashlib.sha256(data).hexdigest(), f'hash mismatch: {relative}'
        assert ('Source: ' + url).encode() in data
        assert article['summary'].strip(), f'empty summary: {relative}'
        # The exporter's header is the ONE H1; a second identical H1 means the
        # page's own title heading leaked into the body (about/, topics/*).
        h1s = re.findall(r'^# ' + re.escape(article['title'].strip()) + r'$', data.decode('utf-8'), re.M)
        assert len(h1s) == 1, f'title H1 appears {len(h1s)}x in export: {relative}'
        assert 'property="og:image"' in html or 'property=og:image' in html, f'missing share image: {relative}'
        if relative.startswith('docs/'):
            assert 'reader-meta' in html and 'data-copy-markdown' in html, f'missing reader controls: {relative}'
    assert set(public.rglob('index.md')) == markdown_paths, 'uncatalogued Markdown output (stale or private page)'
    # Discovery surfaces: the topics index renders tiles (not a bullet list) and
    # the home page renders one image tile per series.
    topics = (public / 'topics' / 'index.html').read_text(encoding='utf-8')
    assert 'reader-topic-index' in topics and topics.count('reader-chip') >= 4, 'topics index lost its tiles/chips'
    home = (public / 'index.html').read_text(encoding='utf-8')
    assert home.count('reader-series-card') == 3, 'home page must render three series image tiles'
    print(f'OK: {len(markdown_paths)} canonical Markdown exports, hashes, share images and populated RSS')


if __name__ == '__main__':
    check(Path(sys.argv[1] if len(sys.argv) > 1 else 'blog/public').resolve())
