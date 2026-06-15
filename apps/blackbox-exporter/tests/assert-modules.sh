#!/usr/bin/env bash
# Assert the GPU-time-share probe modules exist in the blackbox-exporter config
# and that the whole config still validates (blackbox --config.check).
# The config is embedded in configmap.yaml under data["blackbox.yml"]; we extract
# it with PyYAML (via uv, no system dep) and feed it to the real exporter binary.
# Plan: 2026-06-15--obs--gpu-timeshare-health-probes (Phase 1).
set -euo pipefail
cd "$(dirname "$0")/../../.."   # repo root
CM=apps/blackbox-exporter/manifests/configmap.yaml
BB=/tmp/bb-assert.yml

uv run --quiet --with pyyaml python3 - "$CM" "$BB" <<'PY'
import sys, yaml
cm, out = sys.argv[1], sys.argv[2]
cfg = yaml.safe_load(open(cm))["data"]["blackbox.yml"]
open(out, "w").write(cfg)
mods = yaml.safe_load(cfg).get("modules", {})
missing = [m for m in ("litellm_chat", "comfyui_object_info") if m not in mods]
if missing:
    print("MISSING module(s): " + ", ".join(missing))
    sys.exit(1)

# Guard the high-risk silent-inversion bugs:
errs = []
lc = mods["litellm_chat"]["http"]
if lc.get("bearer_token_file") != "/etc/blackbox-secrets/litellm-master-key":
    errs.append(f"litellm_chat bearer_token_file mismatch: {lc.get('bearer_token_file')}")
# fail_if_body_not_matches_regexp (fail when the expected token is ABSENT). The
# inverse field name, fail_if_body_matches_regexp, would pass on a 500-error body
# — a silent inversion. Assert the correct field is set on both probes.
for m, token in (("litellm_chat", '"choices"'), ("comfyui_object_info", "KSampler")):
    h = mods[m]["http"]
    if "fail_if_body_matches_regexp" in h:
        errs.append(f"{m} uses INVERTED fail_if_body_matches_regexp")
    if token not in str(h.get("fail_if_body_not_matches_regexp", "")):
        errs.append(f"{m} missing fail_if_body_not_matches_regexp {token}")
if errs:
    print("FAIL:\n  - " + "\n  - ".join(errs))
    sys.exit(1)
PY

docker run --rm -v "$BB":/c.yml prom/blackbox-exporter:v0.25.0 \
  --config.check --config.file=/c.yml 2>&1 | tail -1
echo "OK: litellm_chat + comfyui_object_info present and config valid"
