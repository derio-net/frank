"""Guard the `gbrain` retrieval-store sidecar in the hermes-agent-shell pod (frank#759).

A fourth container joins the pod: stock `pgvector/pgvector` (PostgreSQL 18 +
pgvector) on loopback, holding the vectors an external client's CLI needs. It is
deliberately NOT the Hindsight Postgres — #759 withdrew that shape because it
coupled two memory layers with different write patterns and different recovery
expectations, and would have needed an RWO expansion on a volume holding a live
database.

Everything asserted here is invisible in a diff and green in a suite if it is
wrong. The five things that actually break:

  1. `PGDATA` at the mount ROOT. The design gate (spec: "The gate, run during
     design") found the entrypoint CREATING that directory is precisely what
     makes it uid-1000-owned and 0700; the mount root has already been widened
     to 0775 by `fsGroup`, and Postgres refuses a data dir wider than 0750. So
     the guard is on the RELATIONSHIP — PGDATA strictly below the mount — not on
     a literal path.
  2. A kubelet-side probe (`httpGet`/`tcpSocket`) against a server that binds
     127.0.0.1 only. The kubelet probes the POD IP, so such a probe is refused
     forever. The `hindsight` container in the same file paid 37 restarts
     learning this; the probes here must be `exec` + `pg_isready` on loopback.
  3. A `containerPort` for 5434, which would advertise off-pod reachability that
     does not exist.
  4. A silently loosened security posture. The pod's strict non-root +
     cap-drop:ALL stance is what the design gate was run under; if the container
     quietly needs root, the gate no longer describes what is deployed.
  5. Hindsight stops being untouched. #759's whole justification for the revised
     shape is that the memory layer next door does not move: same image, same
     PVC, same 5 Gi, same env, same mount. The withdrawn shape — share Hindsight's
     Postgres, expand its volume — is one edited number away at any time, and
     that edit reads as housekeeping. It is asserted here mechanically rather
     than left to the reviewer noticing what the diff does NOT say.

Where a relationship can be asserted, it is asserted as one: PGDATA against the
mountPath the manifest itself declares, the probe commands against the port the
server args themselves configure. A guard that restates the YAML passes for any
YAML, and breaks on a rename that changed nothing.
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

REPO = Path(__file__).resolve().parents[2]
MANIFESTS = REPO / "apps/hermes-agent-shell/manifests"
HERMES_DEPLOY = MANIFESTS / "deployment.yaml"
GBRAIN_PVC = MANIFESTS / "pvc-gbrain.yaml"
GBRAIN_INITDB_CM = MANIFESTS / "configmap-gbrain-initdb.yaml"
HINDSIGHT_PVC = MANIFESTS / "pvc-hindsight.yaml"

PVC_NAME = "hermes-agent-shell-gbrain"
HINDSIGHT_PVC_NAME = "hermes-agent-shell-hindsight"
NAMESPACE = "hermes-agent-shell"

# Hindsight's size BEFORE this work and AFTER it. #759's original shape expanded
# this 5Gi -> 10Gi to host the retrieval store; that shape was withdrawn
# precisely because the expansion meant an RWO detach on a volume holding a live
# database. Reviving it is a one-character edit that looks like a resize.
HINDSIGHT_STORAGE = "5Gi"

# The Hindsight sidecar's Postgres port. It is baked into that image rather than
# declared here, so it cannot be derived from the manifest — but the two servers
# share this pod's single network namespace, so a collision is a real failure
# and worth asserting against.
HINDSIGHT_PG_PORT = "5433"

# The image entrypoint the ssh sidecar's command wrapper must still exec. The
# FULL contract for that wrapper (snapshot file, BYOK vars, no raw sshd) is owned
# by test_hermes_ssh_byok_env_snapshot.py and is deliberately not duplicated
# here; this file asserts only the non-regression THIS plan could plausibly cause.
SSH_IMAGE_ENTRYPOINT = "/usr/local/bin/hermes-ssh-sidecar-entrypoint.sh"

# The multi-arch INDEX digest, so each node resolves its own architecture.
GBRAIN_IMAGE_REPO = "pgvector/pgvector:0.8.6-pg18"
GBRAIN_IMAGE_DIGEST = (
    "sha256:691673308c99d2161ba298736f3147f1f22d79de2fb7ec93ae9b4afcab870b62"
)

# The anchor for the mount-shape test below. PGDATA is deliberately NOT pinned
# to a literal — see test_gbrain_pgdata_is_a_subdirectory_of_the_mount, which
# reads the mountPath back off the manifest and asserts the relationship.
GBRAIN_MOUNT = "/opt/gbrain"
INITDB_DIR = "/docker-entrypoint-initdb.d"


def _load(path: Path):
    return yaml.safe_load(path.read_text())


def _containers(deploy_path: Path) -> dict:
    spec = _load(deploy_path)["spec"]["template"]["spec"]
    return {c["name"]: c for c in spec["containers"]}


# ── Task 1: the volume and the declarative extension ────────────────────────


def test_gbrain_pvc_is_its_own_longhorn_volume():
    """Its own 10Gi RWO Longhorn PVC — decoupled from Hindsight's lifecycle, and
    (being its own Longhorn volume) auto-joined to the default recurring-job
    backup group with no label to set."""
    pvc = _load(GBRAIN_PVC)

    assert pvc["kind"] == "PersistentVolumeClaim"
    assert pvc["metadata"]["name"] == PVC_NAME
    assert pvc["metadata"]["namespace"] == NAMESPACE
    assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]
    assert pvc["spec"]["storageClassName"] == "longhorn", (
        "must be a real Longhorn volume — that is what makes it auto-join the "
        "default recurring-job backup group"
    )
    assert pvc["spec"]["resources"]["requests"]["storage"] == "10Gi"


def test_gbrain_initdb_configmap_creates_the_vector_extension():
    """The pgvector extension is declarative — a .sql file dropped into the
    image's initdb.d — not a manual psql step after first boot."""
    cm = _load(GBRAIN_INITDB_CM)

    assert cm["kind"] == "ConfigMap"
    assert cm["metadata"]["namespace"] == NAMESPACE

    sql_keys = [k for k in cm["data"] if k.endswith(".sql")]
    assert sql_keys, "the initdb ConfigMap must carry a .sql key"

    body = "\n".join(cm["data"][k] for k in sql_keys).lower()
    assert "create extension" in body, "the init SQL must create an extension"
    assert "vector" in body, "the extension created must be pgvector's `vector`"


# ── Task 2: the gbrain container ────────────────────────────────────────────


def _gbrain() -> dict:
    containers = _containers(HERMES_DEPLOY)
    assert "gbrain" in containers, (
        "the hermes-agent-shell pod must carry a `gbrain` retrieval-store container"
    )
    return containers["gbrain"]


def _env(container: dict) -> dict:
    return {e["name"]: e.get("value") for e in container.get("env", [])}


def _mounts(container: dict) -> dict:
    return {m["mountPath"]: m for m in container.get("volumeMounts", [])}


def _volumes() -> dict:
    spec = _load(HERMES_DEPLOY)["spec"]["template"]["spec"]
    return {v["name"]: v for v in spec.get("volumes", [])}


def _pvc_mount_path(container: dict, claim_name: str) -> str:
    """Where `container` mounts the PVC `claim_name`, read off the manifest.

    Derived rather than hardcoded so the assertions built on it stay true
    through a rename of the mount, the volume or the path.
    """
    volumes = _volumes()
    for mount in container.get("volumeMounts", []):
        volume = volumes.get(mount["name"], {})
        if volume.get("persistentVolumeClaim", {}).get("claimName") == claim_name:
            return mount["mountPath"].rstrip("/")
    raise AssertionError(
        f"container {container['name']!r} mounts no volume backed by PVC {claim_name!r}"
    )


def _configured_port(container: dict) -> str:
    """The port the server is actually told to listen on, parsed from its args.

    The probes are checked against THIS rather than against a literal, so the
    guard fails on the shape that really breaks — a probe and a server that
    disagree about the port — instead of merely restating the manifest.
    """
    for arg in container.get("args", []):
        if arg.startswith("port="):
            return arg.split("=", 1)[1]
    raise AssertionError(
        f"container {container['name']!r} declares no `port=` server arg — the "
        "probes below have nothing to be checked against"
    )


def test_gbrain_image_is_stock_pgvector_pinned_by_digest():
    """Stock upstream image (nothing to build in agent-images), pinned by the
    multi-arch INDEX digest so each node resolves its own architecture."""
    image = _gbrain()["image"]

    assert image.startswith(f"{GBRAIN_IMAGE_REPO}@sha256:"), (
        f"gbrain must run stock {GBRAIN_IMAGE_REPO} pinned by digest, got {image!r}"
    )
    assert image.endswith(f"@{GBRAIN_IMAGE_DIGEST}"), (
        f"gbrain must be pinned to {GBRAIN_IMAGE_DIGEST} — the digest the design "
        f"gate was actually run against, got {image!r}"
    )


def test_gbrain_pgdata_is_a_subdirectory_of_the_mount():
    """PGDATA strictly BELOW the mount root, never AT it.

    The design gate found the entrypoint CREATING that directory is what makes it
    uid-1000-owned and 0700. The mount root has already been widened to 0775 by
    the pod's `fsGroup`, and Postgres refuses a data dir wider than 0750 — so
    pointing PGDATA at the mount root is how this fails, on Longhorn, at first
    boot, in a way no local gate reproduces. Nothing in review, and nothing in a
    `docker run` against a plain volume, sees it: it needs a real kubelet
    re-walking a real fsGroup.

    Both sides of the relationship come off the manifest — the mountPath is read
    back from whichever volumeMount is backed by the gbrain PVC — so renaming the
    mount and PGDATA together stays green, while moving PGDATA up to the root
    fails however either is spelled.
    """
    gbrain = _gbrain()
    mount_path = _pvc_mount_path(gbrain, PVC_NAME)
    pgdata = _env(gbrain)["PGDATA"].rstrip("/")

    assert pgdata != mount_path, (
        f"PGDATA ({pgdata!r}) must not BE the mount root — fsGroup has already "
        "widened that directory to 0775 and Postgres refuses a data dir wider "
        "than 0750, so the container fails at initdb on first boot"
    )
    assert pgdata.startswith(mount_path + "/"), (
        f"PGDATA ({pgdata!r}) must live UNDER the gbrain PVC mount "
        f"({mount_path!r}) — anywhere else and the database does not survive a "
        "pod recreate; the entrypoint creating it there is also what makes it "
        "uid-1000-owned and 0700"
    )


def test_gbrain_env_declares_the_database_and_trust_auth():
    """DB/role names the DSN in the app README depends on, and the `trust` posture
    decision 4 accepted (no Secret means nothing can crashloop the shared pod at
    first boot; `listen_addresses=127.0.0.1` is what bounds it)."""
    env = _env(_gbrain())

    assert env["POSTGRES_DB"] == "gbrain"
    assert env["POSTGRES_USER"] == "gbrain"
    assert env["POSTGRES_HOST_AUTH_METHOD"] == "trust"


def test_gbrain_binds_loopback_only_on_its_own_port():
    """Loopback only, on a port Hindsight is not already using.

    The loopback bind is the entire security boundary for the `trust` auth above
    — with `trust`, `listen_addresses` is the only thing standing between this
    database and anything that can route to the pod. And the two Postgres servers
    share this pod's single network namespace, so the port must differ from the
    Hindsight sidecar's or the second one to start simply fails to bind.
    """
    gbrain = _gbrain()
    args = " ".join(gbrain.get("args", []))

    assert "listen_addresses=127.0.0.1" in args, (
        "gbrain must bind loopback only — `trust` auth has no other boundary"
    )
    assert _configured_port(gbrain) != HINDSIGHT_PG_PORT, (
        f"gbrain must not listen on {HINDSIGHT_PG_PORT} — that is the Hindsight "
        "sidecar's Postgres, and both share this pod's network namespace"
    )


def test_gbrain_mounts_its_own_pvc_and_the_initdb_configmap():
    """The PVC is sidecar-only (not /opt/data, not Hindsight's), and the init SQL
    arrives through the image's initdb.d directory."""
    gbrain = _gbrain()
    mounts = _mounts(gbrain)
    volumes = {
        v["name"]: v
        for v in _load(HERMES_DEPLOY)["spec"]["template"]["spec"].get("volumes", [])
    }

    assert GBRAIN_MOUNT in mounts, f"gbrain must mount its volume at {GBRAIN_MOUNT}"
    data_vol = volumes[mounts[GBRAIN_MOUNT]["name"]]
    assert data_vol.get("persistentVolumeClaim", {}).get("claimName") == PVC_NAME, (
        f"{GBRAIN_MOUNT} must be backed by the {PVC_NAME} PVC"
    )

    assert INITDB_DIR in mounts, (
        f"the init SQL must be mounted at {INITDB_DIR} — that is the only place "
        "the image's entrypoint looks"
    )
    initdb_vol = volumes[mounts[INITDB_DIR]["name"]]
    assert initdb_vol.get("configMap", {}).get("name") == (
        "hermes-agent-shell-gbrain-initdb"
    )


def test_gbrain_runs_strict_non_root():
    """The posture the design gate was run under. If this quietly loosens, the
    gate no longer describes what is deployed."""
    sc = _gbrain()["securityContext"]

    assert sc["runAsUser"] == 1000
    assert sc["runAsGroup"] == 1000
    assert sc["runAsNonRoot"] is True
    assert sc["allowPrivilegeEscalation"] is False
    assert sc["capabilities"]["drop"] == ["ALL"]


def test_gbrain_probes_are_exec_pg_isready_on_loopback():
    """All three probes run INSIDE the container, against loopback, on the port
    the server was actually configured with.

    The kubelet runs httpGet/tcpSocket probes against the POD IP; this server
    binds 127.0.0.1 only, so such a probe is connection-refused forever — the
    container never becomes ready and restarts on a timer while the database
    inside it is perfectly healthy. The `hindsight` container in the same file
    cost 37 restarts learning exactly this, which is why the check is on the
    ABSENCE of the kubelet-side keys and not merely on the presence of `exec`:
    both may be declared, and the kubelet would honour the wrong one.

    The port is read back from the server's own `-c port=` arg, so a probe that
    drifts away from the port Postgres listens on fails here — which is the
    version of this bug that survives review, since a probe naming a plausible
    Postgres port looks right.
    """
    gbrain = _gbrain()
    port = _configured_port(gbrain)

    for probe_name in ("startupProbe", "readinessProbe", "livenessProbe"):
        probe = gbrain.get(probe_name)
        assert probe is not None, f"gbrain must declare a {probe_name}"
        for kubelet_side in ("httpGet", "tcpSocket"):
            assert kubelet_side not in probe, (
                f"{probe_name} must not declare {kubelet_side} — the kubelet dials "
                "the POD IP and gbrain binds 127.0.0.1 only, so it would be "
                "connection-refused forever"
            )
        assert "exec" in probe, (
            f"{probe_name} must be an exec probe — only a command running inside "
            "the container can reach a loopback-only server"
        )
        command = " ".join(probe["exec"]["command"])
        assert "pg_isready" in command, (
            f"{probe_name} must ask Postgres itself whether it is accepting "
            "connections, not merely that a process exists"
        )
        assert "127.0.0.1" in command, (
            f"{probe_name} must probe loopback — the interface the server binds"
        )
        assert port in command, (
            f"{probe_name} probes a different port than the server is configured "
            f"with (`-c port={port}`); a probe on the wrong port either never "
            "passes or passes against the Hindsight database next door"
        )


# ── Task 3: Hindsight is genuinely untouched ────────────────────────────────
#
# The headline claim of #759's revision, turned into assertions. Each of these
# fails on an edit that would read, in a diff, as tidying.


def test_gbrain_and_hindsight_share_no_storage():
    """The two stores are decoupled at the volume, which is what makes their
    recovery independent.

    The withdrawn shape put the retrieval vectors inside Hindsight's Postgres on
    Hindsight's volume, so a Hindsight restore silently took the retrieval store
    back with it. Sharing a volume name — or nesting one mount inside the other,
    which is the subtler way to arrive at the same place — reintroduces exactly
    that coupling while looking like a mount tidy-up.
    """
    containers = _containers(HERMES_DEPLOY)
    gbrain, hindsight = containers["gbrain"], containers["hindsight"]

    gbrain_vols = {m["name"] for m in gbrain.get("volumeMounts", [])}
    hindsight_vols = {m["name"] for m in hindsight.get("volumeMounts", [])}
    shared = gbrain_vols & hindsight_vols
    assert not shared, (
        f"gbrain and hindsight must share no volume, found {sorted(shared)} — a "
        "shared volume is how a Hindsight restore takes the retrieval store with it"
    )

    for g_path in sorted(_mounts(gbrain)):
        for h_path in sorted(_mounts(hindsight)):
            g, h = g_path.rstrip("/"), h_path.rstrip("/")
            assert g != h, f"gbrain and hindsight both mount at {g!r}"
            assert not g.startswith(h + "/"), (
                f"gbrain mounts {g!r} INSIDE hindsight's {h!r} — nested mounts "
                "recouple the two stores' lifecycles"
            )
            assert not h.startswith(g + "/"), (
                f"hindsight mounts {h!r} INSIDE gbrain's {g!r} — nested mounts "
                "recouple the two stores' lifecycles"
            )


def test_hindsight_pvc_still_requests_its_original_size():
    """The withdrawn expansion must not creep back.

    #759 originally grew this volume 5Gi -> 10Gi so it could host the retrieval
    store too, and that expansion was the single riskiest thing in the issue: an
    RWO detach-and-expand on a volume holding a live database. The revised design
    exists to avoid it. Reviving it costs one character and would read as a
    resize, so it is asserted rather than remembered — the retrieval store has
    its own 10Gi volume and Hindsight needs nothing.
    """
    pvc = _load(HINDSIGHT_PVC)

    assert pvc["metadata"]["name"] == HINDSIGHT_PVC_NAME
    assert pvc["spec"]["resources"]["requests"]["storage"] == HINDSIGHT_STORAGE, (
        f"the Hindsight PVC must stay at {HINDSIGHT_STORAGE}. Growing it means an "
        "RWO detach-and-expand on a volume holding a live database — the exact "
        "risk #759's revision was written to avoid. The retrieval store has its "
        "own volume; if it needs more room, grow THAT one."
    )


def test_ssh_container_still_execs_the_image_entrypoint():
    """Non-regression only: Bun arrives through the IMAGE, never through this
    wrapper.

    The sibling agent-images plan adds a runtime to the ssh sidecar, and the
    tempting way to land something like that in a hurry is to prepend it to this
    container's `command`. That would break the BYOK env snapshot the wrapper
    exists for, and skip the entrypoint's host-key + authorized_keys prep. The
    full contract for this script — snapshot path, captured vars, no raw sshd —
    is owned by test_hermes_ssh_byok_env_snapshot.py and is not duplicated here.
    """
    ssh = _containers(HERMES_DEPLOY)["ssh"]
    script = "\n".join((ssh.get("command") or []) + (ssh.get("args") or []))

    assert f"exec {SSH_IMAGE_ENTRYPOINT}" in script, (
        f"the ssh sidecar must still `exec {SSH_IMAGE_ENTRYPOINT}` — this plan "
        "changes the ssh container's IMAGE pin and nothing else about it"
    )


def test_gbrain_declares_no_container_port():
    """No `ports:` entry. Declaring a containerPort for a loopback-only server
    advertises reachability that does not exist — the same reason the Hindsight
    sidecar declares none for 5433."""
    assert not _gbrain().get("ports"), (
        "gbrain must declare NO containerPort — nothing off-pod can reach 5434, "
        "and a declared port would claim otherwise"
    )
