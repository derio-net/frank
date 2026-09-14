#!/usr/bin/env python3
"""Build Hugo and the configured agent exports into public/ (stdlib only)."""
import subprocess
import sys
from pathlib import Path
site=Path(__file__).resolve().parents[1]
if sys.argv[1:]:
    # Not an allowlist: hugo's pflag accepts combined shorthands (-DF) and attached
    # values (-dpublic2), so any pass-through can smuggle drafts, future or expired
    # pages into the catalog and exports. Production builds own public/; use
    # `hugo server` for editorial previews.
    raise SystemExit(f'build-site.py takes no arguments (got {sys.argv[1:]}): production builds own public/ and exclude drafts, future and expired pages; use hugo server for editorial previews')
subprocess.run(['hugo','--minify','--cleanDestinationDir'],cwd=site,check=True)
if (site/'public/content-index.json').exists():
    subprocess.run([sys.executable,str(site/'scripts/export-content.py'),str(site/'public')],check=True)
