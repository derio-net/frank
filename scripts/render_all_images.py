#!/usr/bin/env python3
"""Render every Argo CD Application and audit the container images it deploys.

Walks the two App-of-Apps charts (apps/root, clusters/hop/apps/root), renders each
Application source (`helm template` for charts, `kustomize build` or a plain read
for manifest paths), collects every `image:` value and writes the sorted unique
list to scripts/tests/fixtures/life/rendered-images.txt.

  render_all_images.py            regenerate the snapshot
  render_all_images.py --check    exit 1, listing unpinned images, if any

An image is pinned when it carries a digest or a tag other than `latest`.
Values containing `$(` (Tekton params) or `{{` (unrendered templates) are ignored.
Apps that cannot be rendered are recorded as `# skipped:` lines in the snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "scripts/tests/fixtures/life/rendered-images.txt"
EXEMPTIONS = ROOT / "scripts/tests/fixtures/life/audit-exemptions.txt"
ROOT_CHARTS = [ROOT / "apps/root", ROOT / "clusters/hop/apps/root"]


# NVIDIA ClusterPolicy components that are shipped but switched off with `enabled: false`.
# ONLY these keys are skipped when disabled; any other disabled-looking block is audited.
OPERATOR_COMPONENT_KEYS = frozenset({
    "vgpuManager", "vgpuDeviceManager", "kataManager", "ccManager", "sandboxDevicePlugin",
    "vfioManager", "gds", "gdrcopy", "migManager", "dcgm", "dcgmExporter", "nodeStatusExporter",
    "sandboxWorkloads", "cdi",
})

# A registry-qualified image reference embedded in a larger string (ConfigMap script, args,
# env value). Requires a dotted registry host so URLs/paths do not match; the lookbehind
# keeps `https://host/path` and `a/b.c/d` out.
KNOWN_REGISTRIES = frozenset({
    "docker.io", "registry-1.docker.io", "ghcr.io", "quay.io", "gcr.io", "mirror.gcr.io",
    "registry.k8s.io", "nvcr.io", "public.ecr.aws", "docker.litellm.ai", "k8s.gcr.io",
})
EMBEDDED_REF = re.compile(
    r"(?<![\w/:.@-])((?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?/[A-Za-z0-9._/-]+"
    r"(?::[A-Za-z0-9._-]+)?(?:@sha256:[a-f0-9]{64})?)"
)


# Strings that look like image refs but are not deployed images. Each carries its reason and
# is written to audit-exemptions.txt on every run.
STATIC_EXEMPT = {
    "gcr.io/tekton-releases/catalog/upstream/": "Tekton bundle-resolver docs text in vendored release.yaml",
    "gcr.io/tekton-releases/catalog/upstream/git-clone": "Tekton bundle-resolver docs text in vendored release.yaml",
    "ghcr.io/agentic-stoa/site": "shell variable base in site-promotion script; tag appended at run time",
    "ghcr.io/derio-net/runs-fr": "staging-gate contract; the gated sha tag is substituted at run time",
    "nvcr.io/nvidia": "repository prefix field joined with image+version by the NVIDIA operator",
    "nvcr.io/nvidia/cloud-native": "repository prefix field joined with image+version by the NVIDIA operator",
    "nvcr.io/nvidia/driver": "repository prefix field joined with image+version by the NVIDIA operator",
    "nvcr.io/nvidia/k8s": "repository prefix field joined with image+version by the NVIDIA operator",
}


def embedded_refs(text: str) -> list[str]:
    """Registry-qualified refs inside a free-text string; untagged ones only on known registries."""
    refs = []
    for ref in EMBEDDED_REF.findall(text):
        tagged = "@sha256:" in ref or ":" in ref.rsplit("/", 1)[-1]
        if tagged or ref.split("/", 1)[0] in KNOWN_REGISTRIES:
            refs.append(ref)
    return refs


def iter_images(node, exempt: list[str] | None = None):
    """Yield every container image reference in a parsed document.

    Sources: `image:` string values, NVIDIA-style `{repository, image, version}` triples
    (joined), and registry-qualified refs embedded in any other string value.
    Exemptions are appended to `exempt` so they are never silent.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key in OPERATOR_COMPONENT_KEYS and isinstance(value, dict) and value.get("enabled") is False:
                if exempt is not None:
                    exempt.append(f"disabled-component {key} (enabled: false)")
                continue
            if key.endswith("_image") and isinstance(value, str) and isinstance(
                node.get(f"{key}_version"), str
            ):  # operator CR style: postgres_image + postgres_image_version
                yield f"{value}:{node[f'{key}_version']}"
            elif key.endswith("_image_version") and isinstance(value, str):
                continue
            elif key == "image" and isinstance(value, str):
                repo, ver = node.get("repository"), node.get("version")
                if isinstance(repo, str) and isinstance(ver, str):
                    value = f"{repo}/{value}:{ver}"
                yield value
            else:
                yield from iter_images(value, exempt)
    elif isinstance(node, list):
        for item in node:
            yield from iter_images(item, exempt)
    elif isinstance(node, str):
        yield from embedded_refs(node)


def _is_test_hook(doc) -> bool:
    """Helm `test` hooks (connection-test pods) are never applied by Argo CD."""
    if not isinstance(doc, dict):
        return False
    meta = doc.get("metadata")
    ann = meta.get("annotations") if isinstance(meta, dict) else None
    hook = ann.get("helm.sh/hook") if isinstance(ann, dict) else None
    return isinstance(hook, str) and any(h.strip().startswith("test") for h in hook.split(","))


def rendered_images(rendered_yaml: str, exempt: list[str] | None = None) -> list[str]:
    images: list[str] = []
    for doc in yaml.safe_load_all(rendered_yaml):
        if _is_test_hook(doc):
            if exempt is not None:
                name = (doc.get("metadata") or {}).get("name", "?")
                exempt.append(f"helm-test-hook {doc.get('kind', '?')}/{name}")
            continue
        for image in iter_images(doc, exempt):
            if image in STATIC_EXEMPT:
                if exempt is not None:
                    exempt.append(f"static-exempt {image} :: {STATIC_EXEMPT[image]}")
                continue
            if is_ignored(image) and exempt is not None and image.strip():
                exempt.append(f"unresolved {image}")
            images.append(image)
    return images


def is_ignored(image: str) -> bool:
    return not image.strip() or "$(" in image or "{{" in image


def is_unpinned(image: str) -> bool:
    if "@sha256:" in image or "@sha512:" in image:
        return False
    last = image.rsplit("/", 1)[-1]
    if ":" not in last:
        return True
    return last.rsplit(":", 1)[1] == "latest"


def find_unpinned(rendered_yaml: str) -> list[str]:
    """Return the sorted unique unpinned images in a rendered manifest stream."""
    return sorted(
        {i for i in rendered_images(rendered_yaml) if not is_ignored(i) and is_unpinned(i)}
    )


def _run(cmd: list[str]) -> str:
    cache = os.environ.get("RENDER_CACHE")
    key = None
    if cache:
        blob = " ".join(cmd).encode()
        for flag, arg in zip(cmd, cmd[1:]):
            if flag == "-f" and Path(arg).exists():
                blob += Path(arg).read_bytes()
        key = Path(cache) / hashlib.sha256(blob).hexdigest()
        if key.exists():
            return key.read_text()
    out = _run_uncached(cmd)
    if key:
        key.parent.mkdir(parents=True, exist_ok=True)
        key.write_text(out)
    return out


def _run_uncached(cmd: list[str]) -> str:
    done = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=300)
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip().splitlines()[-1] if done.stderr else "failed")
    return done.stdout


def applications() -> list[dict]:
    apps = []
    for chart in ROOT_CHARTS:
        out = _run(["helm", "template", "root", str(chart.relative_to(ROOT))])
        apps += [d for d in yaml.safe_load_all(out) if d and d.get("kind") == "Application"]
    return apps


def _value_args(source: dict, tmp: Path) -> list[str]:
    args = []
    helm = source.get("helm") or {}
    for vf in helm.get("valueFiles", []):
        path = ROOT / vf.replace("$values/", "")
        if path.exists():
            args += ["-f", str(path)]
    inline = helm.get("valuesObject")
    if inline is None and helm.get("values"):
        inline = yaml.safe_load(helm["values"])
    if inline:
        f = tmp / f"inline-{len(list(tmp.iterdir()))}.yaml"
        f.write_text(yaml.safe_dump(inline))
        args += ["-f", str(f)]
    return args


def kustomize_cmd() -> list[str]:
    """`kustomize build` when installed, else the kubectl-embedded copy."""
    return ["kustomize", "build"] if shutil.which("kustomize") else ["kubectl", "kustomize"]


def exit_code(check: bool, unpinned: list[str], skipped: list[str]) -> int:
    """--check fails on any unpinned image AND on any source that could not be audited."""
    return 1 if check and (unpinned or skipped) else 0


def render_source(app: dict, source: dict, tmp: Path) -> str:
    name = (source.get("helm") or {}).get("releaseName") or app["metadata"]["name"]
    ns = app["spec"]["destination"].get("namespace", "default")
    base = ["helm", "template", name]
    common = ["--namespace", ns, "--include-crds", "--kube-version", "1.35.0"]
    if "chart" in source:
        repo = source["repoURL"]
        if repo.startswith("oci://"):
            target = [f"{repo.rstrip('/')}/{source['chart']}"]
        elif not repo.startswith("http"):
            target = [f"oci://{repo.rstrip('/')}/{source['chart']}"]
        else:
            target = [source["chart"], "--repo", repo]
        return _run(
            base + target + ["--version", str(source["targetRevision"])]
            + common + _value_args(source, tmp)
        )
    path = ROOT / source["path"]
    if (path / "Chart.yaml").exists():
        return _run(base + [str(path)] + common + _value_args(source, tmp))
    if (path / "kustomization.yaml").exists() or (path / "kustomization.yml").exists():
        return _run(kustomize_cmd() + [str(path)])
    pattern = "**/*.y*ml" if (source.get("directory") or {}).get("recurse") else "*.y*ml"
    return "\n---\n".join(
        p.read_text() for p in sorted(path.glob(pattern)) if p.suffix in (".yaml", ".yml")
    )


def collect() -> tuple[set[str], list[str], set[str]]:
    images: set[str] = set()
    skipped: list[str] = []
    exempt: set[str] = set()
    for app in applications():
        sources = app["spec"].get("sources") or [app["spec"]["source"]]
        for source in sources:
            if "ref" in source and "chart" not in source and "path" not in source:
                continue
            with tempfile.TemporaryDirectory() as td:
                try:
                    out = render_source(app, source, Path(td))
                    found: list[str] = []
                    images.update(i for i in rendered_images(out, found) if not is_ignored(i))
                    exempt.update(found)
                except Exception as exc:  # noqa: BLE001 - recorded, never silent
                    skipped.append(f"{app['metadata']['name']}: {exc}")
    return images, skipped, exempt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    images, skipped, exempt = collect()
    bad = sorted(i for i in images if is_unpinned(i))
    if not args.check:
        lines = [f"# skipped: {s}" for s in sorted(skipped)] + sorted(images)
        EXEMPTIONS.write_text(
            "# Everything the image audit deliberately did NOT judge. Regenerated by\n"
            "# scripts/render_all_images.py; review changes here like code.\n"
            + "\n".join(sorted(exempt)) + "\n"
        )
        SNAPSHOT.write_text("\n".join(lines) + "\n")
        print(f"wrote {len(images)} images, {len(skipped)} skipped -> {SNAPSHOT}")
    for s in skipped:
        print(f"skipped: {s}", file=sys.stderr)
    for i in bad:
        print(f"UNPINNED: {i}")
    return exit_code(args.check, bad, skipped)


if __name__ == "__main__":
    sys.exit(main())
