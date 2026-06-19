"""Guard the CrowdSec Caddy-log parsing chain on Talos (containerd).

Talos writes CRI-format container logs (`<ts> stdout F {json}`). The CrowdSec
chart defaults `container_runtime: docker`, which labels the acquisition
`type: docker` → the `docker-logs` parser extracts an empty message from a CRI
line → `caddy-logs` never parses → no scenarios fire → nothing is banned.

The proven fix (cscli explain, end-to-end) is the PAIR:
  - top-level `container_runtime: containerd`  → acquisition `type: containerd`
    → `cri-logs` strips the CRI envelope into a clean Caddy-JSON message
  - the caddy acquisition keeps `program: caddy` → flows to `caddy-logs`'
    `evt.Parsed.program startsWith 'caddy'` filter

Either half alone fails (docker→empty message; containerd-without-program→
caddy-logs filter miss), so this test locks both.
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

REPO = Path(__file__).resolve().parents[2]
VALUES = REPO / "clusters/hop/apps/crowdsec/values.yaml"


def _values():
    return yaml.safe_load(VALUES.read_text())


def test_container_runtime_is_containerd():
    # Talos = containerd. docker (the chart default) silently breaks Caddy-log
    # parsing → zero bans. This is the load-bearing half of the fix.
    assert _values().get("container_runtime") == "containerd", (
        "container_runtime must be 'containerd' on Talos — 'docker' (chart default) "
        "routes CRI logs to docker-logs, which yields an empty message and parses nothing"
    )


def test_caddy_acquisition_sets_program_caddy():
    # cri-logs strips the envelope but does NOT set evt.Parsed.program; the caddy
    # acquisition's `program: caddy` label is what reaches caddy-logs' filter.
    acqs = _values()["agent"]["acquisition"]
    caddy = [a for a in acqs if a.get("program") == "caddy"]
    assert caddy, "agent.acquisition must keep a caddy source with program: caddy"
    for a in caddy:
        assert a.get("namespace") == "caddy-system"
        assert str(a.get("podName", "")).startswith("caddy")
