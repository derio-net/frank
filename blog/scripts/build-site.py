#!/usr/bin/env python3
"""Build Hugo and the configured agent exports into public/ (stdlib only)."""
import subprocess
import sys
from pathlib import Path
site=Path(__file__).resolve().parents[1]
# No pass-through: every caller (blog-ci, deploy-blog, Dockerfile, README) runs
# this bare, and any flag that redirects output or widens the page set
# (--destination/-d, -D, -F, -E, or a pflag cluster like -DF / -dpath) would
# silently break the public/ contract the exporter and the reader gate rely on.
if sys.argv[1:]:
    raise SystemExit('Production builds own public/ and exclude drafts, future and expired pages; use hugo server for editorial previews')
subprocess.run(['hugo','--minify','--cleanDestinationDir'],cwd=site,check=True)
if (site/'public/content-index.json').exists():
    subprocess.run([sys.executable,str(site/'scripts/export-content.py'),str(site/'public')],check=True)
