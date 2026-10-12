#!/usr/bin/env python3
"""Find ArgoCD-tracked objects still co-owned by a hand apply.

Server-side apply removes a field only once no manager owns it. An object that
was once `kubectl apply --server-side`d by hand and later adopted by ArgoCD
keeps that hand manager in `metadata.managedFields`, so when git later drops a
list item the hand manager co-owns (a container, an init container), ArgoCD's
apply strips only the fields it owned alone. The item survives without its
required fields and every sync fails, while the app keeps reporting
Synced/Healthy against its last good revision (frank#827).

Read-only. Feed it `kubectl get ... -o json --show-managed-fields` on stdin:

    kubectl get deploy,sts,ds -A -o json --show-managed-fields \\
      | scripts/stale_field_managers.py

Prints one line per stale entry and exits 1 if any are found, 0 if none.

With `--patch` and exactly one object on stdin, prints a JSON patch that removes
the stale entries instead, each guarded by `test` ops on the entry's manager and
time so the API server refuses it if the list moved in the meantime:

    kubectl -n NS get deploy NAME -o json --show-managed-fields \\
      | scripts/stale_field_managers.py --patch > /tmp/patch.json
    kubectl -n NS patch deploy NAME --type=json --patch-file /tmp/patch.json

Only `managedFields` is touched (metadata, no spec change, no pod roll); the
next ArgoCD sync then owns the fields alone and can remove them.
"""

from __future__ import annotations

import argparse
import json
import sys

TRACKING_ANNOTATION = "argocd.argoproj.io/tracking-id"
ARGOCD_MANAGER = "argocd-controller"


def _objects(payload: dict) -> list[dict]:
    if payload.get("kind", "").endswith("List") and "items" in payload:
        return payload["items"]
    return [payload]


def _keyed_items(fields: dict | None, path: tuple = ()) -> set[tuple]:
    """Paths to every keyed list item (`k:{...}`) a FieldsV1 tree owns."""
    out: set[tuple] = set()
    for key, child in (fields or {}).items():
        here = path + (key,)
        if key.startswith("k:"):
            out.add(here)
        if isinstance(child, dict):
            out |= _keyed_items(child, here)
    return out


def stale_entries(obj: dict) -> list[tuple[int, dict]]:
    """(index, entry) of every hand manager that can block ArgoCD on a tracked
    object:

    - any non-ArgoCD `Apply` manager (a hand `kubectl apply --server-side`, a
      bootstrap `helm` install), and
    - any `Update` manager outside a subresource that co-owns a keyed list item
      with ArgoCD, e.g. a plain client-side `kubectl apply`, which kubectl
      records as an Update by `kubectl-client-side-apply`.

    SSA keeps a field while any manager owns it, whatever the operation. Update
    managers that share no list item with ArgoCD (`kubectl-rollout`'s
    restartedAt, an HPA's replicas, status writers) are normal and are not
    reported.
    """
    meta = obj.get("metadata", {})
    if TRACKING_ANNOTATION not in (meta.get("annotations") or {}):
        return []
    fields = meta.get("managedFields") or []
    argocd_items: set[tuple] = set()
    for f in fields:
        if f.get("manager") == ARGOCD_MANAGER:
            argocd_items |= _keyed_items(f.get("fieldsV1"))
    stale = []
    for i, f in enumerate(fields):
        if f.get("manager") == ARGOCD_MANAGER:
            continue
        if f.get("operation") == "Apply":
            stale.append((i, f))
        elif (f.get("operation") == "Update" and not f.get("subresource")
              and _keyed_items(f.get("fieldsV1")) & argocd_items):
            stale.append((i, f))
    return stale


def _ref(obj: dict) -> str:
    meta = obj["metadata"]
    return f"{meta.get('namespace', '-')}/{obj.get('kind', '?')}/{meta['name']}"


def patch_for(entries: list[tuple[int, dict]]) -> list[dict]:
    ops: list[dict] = []
    # Highest index first: removing a lower one shifts every entry after it.
    for i, f in sorted(entries, key=lambda e: e[0], reverse=True):
        base = f"/metadata/managedFields/{i}"
        ops.append({"op": "test", "path": f"{base}/manager", "value": f["manager"]})
        ops.append({"op": "test", "path": f"{base}/time", "value": f["time"]})
        ops.append({"op": "remove", "path": base})
    return ops


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--patch", action="store_true",
                        help="emit a guarded JSON patch for exactly one object")
    args = parser.parse_args()

    objects = _objects(json.load(sys.stdin))

    if args.patch:
        if len(objects) != 1:
            print(f"--patch needs exactly one object, got {len(objects)}", file=sys.stderr)
            return 2
        entries = stale_entries(objects[0])
        print(json.dumps(patch_for(entries), indent=1))
        return 1 if entries else 0

    found = 0
    for obj in objects:
        for i, f in stale_entries(obj):
            found += 1
            print(f"{_ref(obj)} managedFields[{i}] manager={f['manager']} "
                  f"operation={f['operation']} time={f.get('time', '?')}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
