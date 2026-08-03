"""Guard the `gbrain` retrieval-store sidecar in the hermes-agent-shell pod (frank#759).

A fourth container joins the pod: stock `pgvector/pgvector` (PostgreSQL 18 +
pgvector) on loopback, holding the vectors an external client's CLI needs. It is
deliberately NOT the Hindsight Postgres — #759 withdrew that shape because it
coupled two memory layers with different write patterns and different recovery
expectations, and would have needed an RWO expansion on a volume holding a live
database.

Everything asserted here is invisible in a diff and green in a suite if it is
wrong. The four things that actually break:

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
"""

from pathlib import Path

import yaml  # hard dep (pyproject) — a missing yaml must ERROR, not silently skip

REPO = Path(__file__).resolve().parents[2]
MANIFESTS = REPO / "apps/hermes-agent-shell/manifests"
HERMES_DEPLOY = MANIFESTS / "deployment.yaml"
GBRAIN_PVC = MANIFESTS / "pvc-gbrain.yaml"
GBRAIN_INITDB_CM = MANIFESTS / "configmap-gbrain-initdb.yaml"

PVC_NAME = "hermes-agent-shell-gbrain"
NAMESPACE = "hermes-agent-shell"

# The multi-arch INDEX digest, so each node resolves its own architecture.
GBRAIN_IMAGE_REPO = "pgvector/pgvector:0.8.6-pg18"
GBRAIN_IMAGE_DIGEST = (
    "sha256:691673308c99d2161ba298736f3147f1f22d79de2fb7ec93ae9b4afcab870b62"
)

GBRAIN_MOUNT = "/opt/gbrain"
GBRAIN_PGDATA = "/opt/gbrain/pgdata"
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
    boot, in a way no local gate reproduces. The guard is on the RELATIONSHIP.
    """
    pgdata = _env(_gbrain())["PGDATA"]

    assert pgdata.startswith(GBRAIN_MOUNT + "/"), (
        f"PGDATA ({pgdata!r}) must be a SUBDIRECTORY of the mount {GBRAIN_MOUNT!r} — "
        "at the mount root, fsGroup's 0775 makes Postgres refuse to start"
    )
    assert pgdata.rstrip("/") != GBRAIN_MOUNT, "PGDATA must not be the mount root"
    assert pgdata == GBRAIN_PGDATA


def test_gbrain_env_declares_the_database_and_trust_auth():
    """DB/role names the DSN in the app README depends on, and the `trust` posture
    decision 4 accepted (no Secret means nothing can crashloop the shared pod at
    first boot; `listen_addresses=127.0.0.1` is what bounds it)."""
    env = _env(_gbrain())

    assert env["POSTGRES_DB"] == "gbrain"
    assert env["POSTGRES_USER"] == "gbrain"
    assert env["POSTGRES_HOST_AUTH_METHOD"] == "trust"


def test_gbrain_binds_loopback_only_on_its_own_port():
    """5434 on loopback — 5432 is unused, 5433 is Hindsight's. The loopback bind
    is the entire security boundary for the `trust` auth above."""
    args = " ".join(_gbrain().get("args", []))

    assert "listen_addresses=127.0.0.1" in args, (
        "gbrain must bind loopback only — `trust` auth has no other boundary"
    )
    assert "port=5434" in args, (
        "gbrain must listen on 5434 (5433 is the Hindsight sidecar's Postgres)"
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
    """All three probes run INSIDE the container against 127.0.0.1.

    The kubelet runs httpGet/tcpSocket probes against the POD IP; this server
    binds loopback only, so such a probe is connection-refused forever. The
    `hindsight` container in the same file cost 37 restarts learning exactly this.
    """
    gbrain = _gbrain()

    for probe_name in ("startupProbe", "readinessProbe", "livenessProbe"):
        probe = gbrain.get(probe_name)
        assert probe is not None, f"gbrain must declare a {probe_name}"
        assert "httpGet" not in probe and "tcpSocket" not in probe, (
            f"{probe_name} must not be a kubelet-side probe — the kubelet dials the "
            "POD IP and gbrain binds 127.0.0.1 only, so it would be refused forever"
        )
        command = " ".join(probe["exec"]["command"])
        assert "pg_isready" in command, f"{probe_name} must probe with pg_isready"
        assert "127.0.0.1" in command, f"{probe_name} must probe loopback"
        assert "5434" in command, f"{probe_name} must probe gbrain's port, not 5433"


def test_gbrain_declares_no_container_port():
    """No `ports:` entry. Declaring a containerPort for a loopback-only server
    advertises reachability that does not exist — the same reason the Hindsight
    sidecar declares none for 5433."""
    assert not _gbrain().get("ports"), (
        "gbrain must declare NO containerPort — nothing off-pod can reach 5434, "
        "and a declared port would claim otherwise"
    )
