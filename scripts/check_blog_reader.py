#!/usr/bin/env python3
"""Check the public reader contract after blog/scripts/build-site.py."""
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse


def check(public):
    catalog = json.loads((public / 'content-index.json').read_text())
    base = 'https://blog.derio.net/frank/'
    assert catalog['site'] == base, 'catalog canonical URL drifted'
    assert catalog['schema_version'] == 1
    assert catalog['articles'], 'empty catalog'
    assert 'content-index.json' in (public / 'llms.txt').read_text()
    assert ET.parse(public / 'index.xml').findall('./channel/item'), 'empty RSS feed'
    markdown_paths = set()
    for article in catalog['articles']:
        url = article['url']
        assert url.startswith(base), f'noncanonical URL: {url}'
        relative = unquote(urlparse(url).path).removeprefix('/frank/')
        directory = (public / relative).resolve()
        assert directory.is_relative_to(public), f'path outside public: {relative}'
        html = (directory / 'index.html').read_text()
        path = directory / 'index.md'
        markdown_paths.add(path)
        data = path.read_bytes()
        assert article['markdown_url'] == url + 'index.md'
        assert article['content_sha256'] == hashlib.sha256(data).hexdigest(), f'hash mismatch: {relative}'
        assert ('Source: ' + url).encode() in data
        assert article['summary'].strip(), f'empty summary: {relative}'
        assert 'property="og:image"' in html or 'property=og:image' in html, f'missing share image: {relative}'
        if relative.startswith('docs/'):
            assert 'reader-meta' in html and 'data-copy-markdown' in html, f'missing reader controls: {relative}'
    assert set(public.rglob('index.md')) == markdown_paths, 'uncatalogued Markdown output (stale or private page)'
    print(f'OK: {len(markdown_paths)} canonical Markdown exports, hashes, share images and populated RSS')


if __name__ == '__main__':
    check(Path(sys.argv[1] if len(sys.argv) > 1 else 'blog/public').resolve())
