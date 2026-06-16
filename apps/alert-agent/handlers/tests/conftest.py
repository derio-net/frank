"""Put the sibling frank-facts + telegram-bridge package roots on sys.path so the
handlers can import frank_facts + tg_bridge (mirrors the pod's PYTHONPATH)."""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # apps/alert-agent
for pkg in ("frank-facts", "telegram-bridge", "handlers"):
    sys.path.insert(0, os.path.join(HERE, pkg))
