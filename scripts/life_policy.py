#!/usr/bin/env python3
"""Update policy: which of the four update paths every dependency takes (spec R5).

  life_policy.py --emit-facts      render every Application, write app-facts.yaml
  life_policy.py --emit-renovate   print renovate.json5 generated from update-policy.yaml

The policy file (update-policy.yaml) is the single source; renovate.json5 is generated
from it so the two cannot drift. The update CONSOLE merges, never Renovate (automerge
is false everywhere).
"""

from __future__ import annotations

import argparse
import fnmatch
import functools
import json
import re
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY_FILE = ROOT / "update-policy.yaml"
FACTS_FILE = ROOT / "scripts/tests/fixtures/life/app-facts.yaml"
RENOVATE_FILE = ROOT / "renovate.json5"

PATHS = ("auto-merge", "batch-approve", "session", "operator-runbook")
RANK = {p: i for i, p in enumerate(PATHS)}  # a stricter path outranks a looser one
UPDATE_TYPES = ("patch", "minor", "major")
CHART_ROOTS = (("frank", "apps/root"), ("hop", "clusters/hop/apps/root"))
STATE_KEYS = ("volumeClaimTemplates", "volumeClaimTemplate", "persistentVolumeClaim")
STATE_KINDS = frozenset({"AWX", "VMSingle", "VLSingle", "VMCluster", "PersistentVolumeClaim"})
# Only workload kinds are inspected for claim templates: a Tekton TriggerTemplate/Pipeline that
# MENTIONS a PVC shape (volumeClaimTemplate) owns no state itself.
WORKLOAD_KINDS = frozenset({"StatefulSet", "Deployment", "DaemonSet", "Job", "CronJob", "Rollout"})
# Stateful by identity, not by an owned claim: Longhorn is the storage layer for every PVC.
STATEFUL_BY_IDENTITY = frozenset({"frank/longhorn", "frank/longhorn-extras"})
DEP_NAMES = {  # policy dep -> Renovate depName (see the customManagers below)
    "talos:frank": "siderolabs/talos", "talos:hop": "siderolabs/talos",
    "kubernetes:frank": "kubernetes/kubernetes", "kubernetes:hop": "kubernetes/kubernetes",
    "omni": "siderolabs/omni",
}
BATCH_GROUP = "routine-updates"


# --------------------------------------------------------------------- enumeration
@functools.lru_cache(maxsize=None)
def applications() -> tuple[dict, ...]:
    """Every Application in both root charts: {cluster, name, spec, key}."""
    import render_all_images as r

    out = []
    for cluster, chart in CHART_ROOTS:
        rendered = r._run(["helm", "template", "root", chart])
        for d in yaml.safe_load_all(rendered):
            if d and d.get("kind") == "Application":
                out.append({"cluster": cluster, "name": d["metadata"]["name"],
                            "key": f"{cluster}/{d['metadata']['name']}", "app": d})
    return tuple(out)


def app_keys() -> list[str]:
    return [a["key"] for a in applications()]


# --------------------------------------------------------------------- policy
def load_policy() -> dict:
    return yaml.safe_load(POLICY_FILE.read_text())


def load_facts() -> dict:
    return yaml.safe_load(FACTS_FILE.read_text())["apps"]


def image_repo(image: str) -> str:
    """registry/path of an image reference without its tag or digest."""
    ref = image.split("@")[0]
    head, _, last = ref.rpartition("/")
    return f"{head}/{last.split(':')[0]}" if head else last.split(":")[0]


def _matches(rule: dict, kind: str, value: str, update: str) -> bool:
    if kind == "image":
        value = image_repo(value)
    pat = rule["match"].get(kind)
    if pat is None or not fnmatch.fnmatchcase(value, pat):
        return False
    return update in rule.get("update", UPDATE_TYPES)


def _first(policy: dict, kind: str, value: str, update: str) -> str | None:
    for rule in policy["rules"]:
        if _matches(rule, kind, value, update):
            return rule["path"]
    return None


def resolve(dep: dict, update: str = "patch", policy: dict | None = None,
            facts: dict | None = None) -> str:
    """The single update path of a dependency: {app|image|chart|dep: name}."""
    policy = policy or load_policy()
    (kind, value), = dep.items()
    if kind in ("app", "dep"):
        return _first(policy, kind, value, update) or policy["defaults"][update]
    facts = facts or load_facts()
    explicit = _first(policy, kind, value, update)
    field = "images" if kind == "image" else "charts"
    owners = [a for a, f in facts.items() if value in f[field]]
    paths = [resolve({"app": a}, update, policy, facts) for a in owners]
    if explicit:
        paths.append(explicit)
    if not paths:
        return policy["defaults"][update]
    return max(paths, key=RANK.__getitem__)


# --------------------------------------------------------------------- facts
def _walk(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def doc_flags(rendered: str) -> tuple[bool, bool]:
    """(owns persistent state, is an Argo Rollouts app) for rendered YAML."""
    stateful = rollout = False
    for d in yaml.safe_load_all(rendered):
        if not isinstance(d, dict):
            continue
        if d.get("kind") == "Rollout" and str(d.get("apiVersion", "")).startswith("argoproj.io"):
            rollout = True
        if d.get("kind") in STATE_KINDS:
            stateful = True
        if d.get("kind") in WORKLOAD_KINDS and any(k in STATE_KEYS for k in _walk(d)):
            stateful = True
    return stateful, rollout


def _template_files() -> dict[str, str]:
    """Application name -> the root-chart template file that declares it (cluster-qualified)."""
    out = {}
    for cluster, chart in CHART_ROOTS:
        for f in sorted((ROOT / chart / "templates").glob("*.yaml")):
            m = re.search(r"^kind: Application\s*\nmetadata:\s*\n\s+name: (\S+)", f.read_text(), re.M)
            if m:
                out[f"{cluster}/{m.group(1)}"] = str(f.relative_to(ROOT))
    return out


def app_paths(entry: dict, template: str | None) -> list[str]:
    """Repo globs whose changes belong to this app (for Renovate matchFileNames)."""
    spec = entry["app"]["spec"]
    paths: list[str] = [template] if template else []
    for s in spec.get("sources") or [spec["source"]]:
        if "chart" not in s and s.get("path"):
            paths.append(s["path"].rstrip("/") + "/**")
        for vf in (s.get("helm") or {}).get("valueFiles", []):
            paths.append(vf.replace("$values/", ""))
    return sorted(set(paths))


def collect_facts() -> dict:
    import render_all_images as r

    templates = _template_files()
    facts = {}
    for entry in applications():
        app = entry["app"]
        spec = app["spec"]
        stateful = rollout = False
        images: set[str] = set()
        charts: set[str] = set()
        services: list[dict] = []
        dest_ns = spec["destination"].get("namespace", "default")
        for s in spec.get("sources") or [spec["source"]]:
            if "ref" in s and "chart" not in s and "path" not in s:
                continue
            if "chart" in s:
                charts.add(s["chart"])
            with tempfile.TemporaryDirectory() as td:
                out = r.render_source(app, s, Path(td))
            st, ro = doc_flags(out)
            stateful, rollout = stateful or st, rollout or ro
            images.update(i for i in r.rendered_images(out, []) if not r.is_ignored(i))
            for d in yaml.safe_load_all(out):
                if isinstance(d, dict) and d.get("kind") == "Service":
                    services.append({"name": d["metadata"]["name"],
                                     "namespace": d["metadata"].get("namespace") or dest_ns,
                                     "ports": sorted({p.get("port") for p in d["spec"].get("ports", [])})})
        facts[entry["key"]] = {
            "stateful": stateful or entry["key"] in STATEFUL_BY_IDENTITY, "rollout": rollout,
            "charts": sorted(charts), "images": sorted(images),
            "services": sorted(services, key=lambda x: (x["name"], x["namespace"])),
            "paths": app_paths(entry, templates.get(entry["key"])),
        }
    return facts


def detect_offline() -> dict[str, tuple[bool, bool]]:
    """Re-detect stateful/rollout for git-resident (non-remote-chart) sources; no network."""
    import render_all_images as r

    seen = {}
    for entry in applications():
        app = entry["app"]
        spec = app["spec"]
        st = ro = False
        for s in spec.get("sources") or [spec["source"]]:
            if "chart" in s or ("ref" in s and "path" not in s):
                continue
            with tempfile.TemporaryDirectory() as td:
                out = r.render_source(app, s, Path(td))
            a, b = doc_flags(out)
            st, ro = st or a, ro or b
        seen[entry["key"]] = (st, ro)
    return seen


# --------------------------------------------------------------------- renovate
def _attrs(path: str) -> dict:
    needs_approval = path in ("session", "operator-runbook")
    return {
        "labels": [f"path:{path}"],
        "automerge": False,
        "groupName": BATCH_GROUP if path == "batch-approve" else None,
        "dependencyDashboardApproval": needs_approval,
        **({"minimumReleaseAge": "3 days"} if path in ("auto-merge", "batch-approve") else {}),
    }


def renovate_config(policy: dict | None = None, facts: dict | None = None) -> dict:
    policy = policy or load_policy()
    facts = facts or load_facts()
    rules: list[dict] = []
    for ut in UPDATE_TYPES:
        p = policy["defaults"][ut]
        rules.append({"description": f"default path for {ut} updates: {p}",
                      "matchUpdateTypes": [ut], **_attrs(p)})
    grouped: dict[tuple, dict] = {}
    for rule in policy["rules"]:
        (kind, value), = rule["match"].items()
        upd = tuple(rule.get("update", UPDATE_TYPES))
        g = grouped.setdefault((rule["path"], upd), {"files": set(), "pkgs": set(), "deps": set()})
        if kind == "app":
            for pat, f in facts.items():
                if fnmatch.fnmatchcase(pat, value):
                    g["files"].update(f["paths"])
                    g["pkgs"].update(f["charts"])
        elif kind in ("image", "chart"):
            g["pkgs"].add(value)
        else:
            g["deps"].add(DEP_NAMES[value])
    for (path, upd), g in grouped.items():
        base = {"matchUpdateTypes": list(upd)} if upd != UPDATE_TYPES else {}
        for key, field, what in (("files", "matchFileNames", "files"), ("pkgs", "matchPackageNames", "packages"),
                                 ("deps", "matchDepNames", "dependencies")):
            if g[key]:
                rules.append({"description": f"{path}: {what} ({', '.join(upd)})",
                              field: sorted(g[key]), **base, **_attrs(path)})
    return {
        "$schema": "https://docs.renovatebot.com/renovate-schema.json",
        "automerge": False,
        "platformAutomerge": False,
        "dependencyDashboard": True,
        "dependencyDashboardTitle": "Dependency Dashboard (frank)",
        "enabledManagers": ["argocd", "helm-values", "kubernetes", "kustomize", "custom.regex"],
        "argocd": {"fileMatch": [r"^apps/root/templates/.+\.ya?ml$", r"^clusters/hop/apps/root/templates/.+\.ya?ml$"]},
        "helm-values": {"fileMatch": [r"(^|/)values\.ya?ml$"]},
        "kubernetes": {"fileMatch": [r"^apps/.+/manifests/.+\.ya?ml$", r"^clusters/hop/apps/.+/manifests/.+\.ya?ml$"]},
        "kustomize": {"fileMatch": [r"(^|/)kustomization\.ya?ml$"]},
        "customManagers": [
            {"customType": "regex", "fileMatch": [r"^versions/frank\.yaml$", r"^versions/hop\.yaml$"],
             "matchStrings": [r"(?m)^talos: (?<currentValue>\S+)"],
             "depNameTemplate": "siderolabs/talos", "datasourceTemplate": "github-releases",
             "extractVersionTemplate": "^v(?<version>.+)$"},
            {"customType": "regex", "fileMatch": [r"^versions/frank\.yaml$", r"^versions/hop\.yaml$"],
             "matchStrings": [r"(?m)^kubernetes: (?<currentValue>\S+)"],
             "depNameTemplate": "kubernetes/kubernetes", "datasourceTemplate": "github-releases",
             "extractVersionTemplate": "^v(?<version>.+)$"},
            {"customType": "regex", "fileMatch": [r"^omni/omni/omni\.env\.template$"],
             "matchStrings": [r"(?m)^OMNI_VERSION=(?<currentValue>\S+)"],
             "depNameTemplate": "siderolabs/omni", "datasourceTemplate": "github-releases"},
        ],
        "vulnerabilityAlerts": {"enabled": True, "labels": ["security"], "automerge": False},
        "packageRules": rules,
    }


def emit_renovate(policy: dict | None = None, facts: dict | None = None) -> str:
    header = (
        "// GENERATED by scripts/life_policy.py --emit-renovate from update-policy.yaml.\n"
        "// Do not edit by hand: a test fails when this file differs from the emitted one.\n"
        "// automerge is false EVERYWHERE: the update console merges, after CI and the countdown.\n"
    )
    return header + json.dumps(renovate_config(policy, facts), indent=2) + "\n"


def main() -> int:
    sys.path.insert(0, str(Path(__file__).parent))
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit-facts", action="store_true")
    ap.add_argument("--emit-renovate", action="store_true")
    ap.add_argument("--write", action="store_true", help="write renovate.json5 instead of printing")
    a = ap.parse_args()
    if a.emit_facts:
        FACTS_FILE.write_text(
            "# GENERATED by scripts/life_policy.py --emit-facts (renders every Application).\n"
            + yaml.safe_dump({"apps": collect_facts()}, sort_keys=True, width=200))
        print(f"wrote {FACTS_FILE}")
    if a.emit_renovate:
        text = emit_renovate()
        if a.write:
            RENOVATE_FILE.write_text(text)
        else:
            sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
