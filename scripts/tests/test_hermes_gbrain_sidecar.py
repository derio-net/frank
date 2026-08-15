"""Guard the `gbrain` retrieval-store sidecar in the hermes-agent-shell pod (frank#759).

A fourth container joins the pod: stock `pgvector/pgvector` (PostgreSQL 18 +
pgvector) on loopback, holding the vectors an external client's CLI needs. It is
deliberately NOT the Hindsight Postgres — #759 withdrew that shape because it
coupled two memory layers with different write patterns and different recovery
expectations, and would have needed an RWO expansion on a volume holding a live
database.

Everything asserted here is invisible in a diff and green in a suite if it is
wrong. The five things that actually break:

  1. `PGDATA` at the mount ROOT. The stock entrypoint runs
     `chmod 00700 "$PGDATA" || :` on EVERY start, before the "already
     initialised" branch. Because the container CREATES and OWNS the
     subdirectory, that chmod SUCCEEDS — which is both why the strict posture
     works and why an fsGroup re-walk that re-loosens a populated PGDATA is put
     back to 0700 at the next boot. Point PGDATA at the mount root instead —
     which the pod-level `fsGroup` leaves at root:1000 2775 — and the identical
     chmod EPERMs on a root-owned directory, is SWALLOWED by the `|| :`, and
     initdb then dies on its own chmod ("could not change permissions of
     directory"). So the guard is on the RELATIONSHIP — PGDATA strictly below
     the mount — not on a literal path.

     (An earlier draft of this file explained it as "the mount root is 0775 and
     Postgres refuses a data dir wider than 0750". That is NOT the mechanism:
     the volume root is 2775, and the 0750 postmaster check is only reachable
     had it got past the chmod. Corrected 2026-08-03 and reproduced on the
     pinned digest; the runbook and `deployment.yaml` carry the same correction.)
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
     shape is that the memory layer next door does not move. The withdrawn shape
     — share Hindsight's Postgres, expand its volume — is one edited number away
     at any time, and that edit reads as housekeeping.

     SCOPE, precisely: what is asserted here is that Hindsight's PVC still
     requests its original 5 Gi, and that the two containers share no volume,
     no mount path and NO PVC `claimName`. Hindsight's image and env are NOT
     asserted — deliberately, because its image tag is moved by the agent-images
     bump workflow and a guard pinning it would fight a scheduled robot every
     month. "Same image, same env" is a statement about what this plan does, not
     a property this file mechanically enforces.

Where a relationship can be asserted, it is asserted as one: PGDATA against the
mountPath the manifest itself declares, the probe commands against the port the
server args themselves configure. A guard that restates the YAML passes for any
YAML, and breaks on a rename that changed nothing.

And where a property is a SET rather than a substring, it is parsed rather than
grepped. Two guards here were vacuous to a last-wins override or an indirection
before the 2026-08-03 review: `-c` server flags are parsed into a dict (Postgres
applies them left-to-right, so APPENDING `-c listen_addresses=0.0.0.0` beat an
`in`-the-joined-args check while binding every interface), and the storage
disjointness runs on resolved `claimName`s (comparing volume NAMES let two
distinct names point at one PVC).
"""

import re
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

# ONE constant, asserted on BOTH sides — the ConfigMap's own metadata.name and
# the deployment volume that references it. Anchored on one side only, a rename
# passes green and then fails the KUBELET: the volume is not `optional: true`,
# so an unresolvable ConfigMap leaves the WHOLE POD in ContainerCreating, taking
# hermes, ssh and hindsight down with it on a `Recreate` deployment.
INITDB_CM_NAME = "hermes-agent-shell-gbrain-initdb"

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
    assert cm["metadata"]["name"] == INITDB_CM_NAME, (
        f"the initdb ConfigMap must be named {INITDB_CM_NAME!r} — the deployment "
        "references it by that name in a volume that is NOT optional, so a "
        "rename here does not fail this test, it fails the KUBELET: the whole "
        "pod sticks in ContainerCreating and hermes/ssh/hindsight go down with it"
    )

    sql_keys = [k for k in cm["data"] if k.endswith(".sql")]
    assert sql_keys, "the initdb ConfigMap must carry a .sql key"

    # ONE regex, not two independent substrings. Two `in` checks over the
    # concatenation of every .sql key pass on `CREATE EXTENSION hstore;` in one
    # key plus the word "vector" in a COMMENT in another — the extension the
    # store exists for silently absent, the guard green.
    body = "\n".join(cm["data"][k] for k in sql_keys)
    assert re.search(
        r"create\s+extension\s+(if\s+not\s+exists\s+)?vector\b", body, re.IGNORECASE
    ), (
        "the init SQL must actually CREATE EXTENSION vector — this is the only "
        f"place pgvector gets enabled, and it is read once, at initdb. Got: {body!r}"
    )


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


def _claim_names(container: dict) -> set:
    """The PVC `claimName`s this container actually mounts, resolved through the
    pod's volume list.

    The indirection is the whole point. Two volumes with entirely different
    NAMES and different mountPaths can name the SAME `claimName`, which is one
    RWO Longhorn volume with two Postgres instances on it — precisely the
    coupling #759's revision exists to prevent, arrived at by an edit that
    touches neither a name nor a path.
    """
    volumes = _volumes()
    claims = set()
    for mount in container.get("volumeMounts", []):
        claim = (
            volumes.get(mount["name"], {})
            .get("persistentVolumeClaim", {})
            .get("claimName")
        )
        if claim:
            claims.add(claim)
    return claims


def _server_settings(container: dict) -> dict:
    """Every `-c key=value` server flag, parsed, with LAST-WINS semantics.

    PostgreSQL applies `-c` settings left to right, so a later flag silently
    overrides an earlier one. That makes any substring check over the joined
    args VACUOUS to an append: adding `-c listen_addresses=0.0.0.0` to the end
    leaves `listen_addresses=127.0.0.1` present in the string while the server
    binds every interface — and with `POSTGRES_HOST_AUTH_METHOD=trust` that is
    `host all all all trust`, i.e. unauthenticated superuser Postgres reachable
    from anything that can route to the pod IP.

    `listen_addresses` is described in the spec as "the only thing standing
    between this database and anything that can route to the pod", so it is the
    one setting that must not be assertable by substring. Parse, do not grep.

    KEYS ARE NORMALISED, and that is not cosmetic. Postgres does not compare GUC
    names verbatim: `ParseLongOption` rewrites `-` to `_`, and GUC lookup is
    case-insensitive. So the FIRST version of this parser — which stored
    `key.strip()` as written — was still bypassable by the two spellings nobody
    had mutated, even though it had just been "upgraded" from a substring check
    precisely to close this hole (2026-08-15 review):

        -c LISTEN_ADDRESSES=0.0.0.0   -> stored as 'LISTEN_ADDRESSES'
        --listen-addresses=0.0.0.0    -> stored as 'listen-addresses'

    Neither collides with the `listen_addresses` the assertion reads, so the
    guard stayed green while the server bound every interface — with `trust`,
    unauthenticated superuser Postgres on the pod IP. Normalising on write is
    what makes the parse actually model Postgres rather than merely look like it.

    Three arg SHAPES are recognised, because the guard is only as good as the
    spellings it can see: `-c key=value` (split or joined) and `--key=value`,
    plus the space-separated `--key value` long form. Recognising more shapes can
    only make this stricter — an unrecognised shape is one the server honours and
    the test cannot see.
    """

    def _norm(key: str) -> str:
        # Mirror ParseLongOption: hyphens are underscores, lookup is case-insensitive.
        return key.strip().lower().replace("-", "_")

    settings: dict = {}
    args = list(container.get("args", []))
    i = 0
    while i < len(args):
        arg, consumed = args[i], 1
        if arg == "-c" and i + 1 < len(args):
            arg, consumed = args[i + 1], 2
        elif arg.startswith("-c") and len(arg) > 2:
            arg = arg[2:]
        elif arg.startswith("--") and "=" in arg:
            arg = arg[2:]
        elif (
            arg.startswith("--")
            and i + 1 < len(args)
            and not args[i + 1].startswith("-")
        ):
            # `--listen-addresses 0.0.0.0` — the space-separated long form.
            settings[_norm(arg[2:])] = args[i + 1].strip()
            i += 2
            continue
        else:
            i += 1
            continue
        if "=" in arg:
            key, value = arg.split("=", 1)
            settings[_norm(key)] = value.strip()  # LAST wins, as postgres does
        i += consumed
    return settings


def _configured_port(container: dict) -> str:
    """The port the server is actually told to listen on, parsed from its args.

    The probes are checked against THIS rather than against a literal, so the
    guard fails on the shape that really breaks — a probe and a server that
    disagree about the port — instead of merely restating the manifest. Uses the
    same last-wins parse as everything else: an appended `-c port=…` moves the
    server, and the probes have to move with it.
    """
    settings = _server_settings(container)
    if "port" not in settings:
        raise AssertionError(
            f"container {container['name']!r} declares no `port=` server arg — the "
            "probes below have nothing to be checked against"
        )
    return settings["port"]


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

    The stock entrypoint runs `chmod 00700 "$PGDATA" || :` on every start.
    Because the container CREATES and OWNS the subdirectory, that chmod succeeds.
    Point PGDATA at the mount root — which the pod's `fsGroup` leaves at
    root:1000 2775 — and the same chmod EPERMs on a root-owned directory, is
    swallowed by the `|| :`, and initdb dies on its own chmod. That is how this
    fails: at first boot, with the real error several lines away from the real
    cause.

    Both sides of the relationship come off the manifest — the mountPath is read
    back from whichever volumeMount is backed by the gbrain PVC — so renaming the
    mount and PGDATA together stays green, while moving PGDATA up to the root
    fails however either is spelled.
    """
    gbrain = _gbrain()
    mount_path = _pvc_mount_path(gbrain, PVC_NAME)
    pgdata = _env(gbrain)["PGDATA"].rstrip("/")

    assert pgdata != mount_path, (
        f"PGDATA ({pgdata!r}) must not BE the mount root — fsGroup leaves that "
        "directory root-owned (root:1000 2775), so the entrypoint's "
        "`chmod 00700 $PGDATA` EPERMs, is swallowed by its `|| :`, and initdb "
        "then dies on its own chmod at first boot"
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

    Asserted on the PARSED, last-wins value rather than on a substring of the
    joined args: `-c` settings are applied left to right, so appending
    `-c listen_addresses=0.0.0.0` satisfies an `in` check while the server binds
    everything — and `trust` + every interface is unauthenticated superuser
    Postgres on the pod IP.
    """
    gbrain = _gbrain()
    settings = _server_settings(gbrain)

    assert settings.get("listen_addresses") == "127.0.0.1", (
        "gbrain must bind loopback ONLY — `trust` auth has no other boundary. "
        f"The effective (last-wins) listen_addresses is "
        f"{settings.get('listen_addresses')!r}; anything but '127.0.0.1' exposes "
        "an unauthenticated superuser Postgres on the pod IP"
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
    assert initdb_vol.get("configMap", {}).get("name") == INITDB_CM_NAME, (
        f"the initdb volume must reference the {INITDB_CM_NAME!r} ConfigMap — the "
        "SAME constant the ConfigMap's own metadata.name is asserted against, so "
        "a rename cannot pass by moving both sides' literals independently"
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
    assert sc.get("seccompProfile", {}).get("type") == "RuntimeDefault", (
        "gbrain must set seccompProfile RuntimeDefault — with the five settings "
        "above it is the only field between this container and a clean "
        "`restricted` audit, which the namespace warns at"
    )


def test_gbrain_pins_the_collation_provider_at_initdb():
    """The collation provider is a FIRST-BOOT-ONLY decision, so it is guarded.

    With no POSTGRES_INITDB_ARGS the image's `ENV LANG en_US.utf8` wins and
    initdb builds the cluster under the LIBC provider — measured on the pinned
    digest: datlocprovider 'c', datcollate 'en_US.utf8'. That binds collation to
    the glibc inside the image, so a later image rebuild emits `collation version
    mismatch` and every text/btree index needs REINDEX.

    This is guarded rather than merely commented because the window to fix it
    closes the instant the volume initialises: after first boot the entrypoint
    skips initdb entirely, and changing this env var does nothing at all. A
    deleted line here is silent today and expensive later — the worst shape.

    Measured 2026-08-15 on the pinned digest (amd64): with the arg,
    datlocprovider 'b', datlocale 'C.UTF-8', pgvector 0.8.6 still installs from
    initdb.d, an hnsw index builds and answers; on an already-initialised volume
    the arg is an inert no-op.
    """
    args = _env(_gbrain()).get("POSTGRES_INITDB_ARGS", "")

    assert "--locale-provider=builtin" in args, (
        "gbrain must pin the BUILTIN locale provider at initdb — without it the "
        f"cluster inherits libc/en_US.utf8 from the image's LANG (got {args!r}), "
        "and that binds the collation to the image's glibc version forever"
    )
    assert "--builtin-locale=C.UTF-8" in args, (
        "the builtin provider needs an explicit builtin locale; C.UTF-8 matches "
        f"the hindsight sidecar's baked recipe (got {args!r})"
    )


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

    for probe_name in ("startupProbe", "livenessProbe"):
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


def test_gbrain_declares_no_readiness_probe():
    """gbrain must NOT have a readinessProbe — its absence is a decision.

    Pod `Ready` is an ALL-containers condition, and service.yaml selects this pod
    with no `publishNotReadyAddresses`. So a readiness failure in this sidecar
    withdraws the whole pod from 192.168.55.226 — SSH (22 -> 2222) and all
    sixteen mosh ports included. The failure mode is self-blocking: the store you
    would log in to debug is what removed the way in.

    It would also gate nothing. Readiness governs SERVICE ENDPOINTS; gbrain
    declares no `ports:` and no Service routes to it, so the probe is pure
    downside. Container health remains supervised by startup + liveness.

    This is asserted rather than merely commented because re-adding a
    readinessProbe is the single most natural-looking edit anyone could make to
    this block — every sibling container has one, so it reads as an omission. It
    is not; `ssh` keeps its readinessProbe precisely because there the
    LB-withdrawal IS the wanted behaviour.
    """
    gbrain = _gbrain()

    assert "readinessProbe" not in gbrain, (
        "gbrain must NOT declare a readinessProbe: pod Ready is all-containers "
        "and the LoadBalancer Service has no publishNotReadyAddresses, so this "
        "sidecar going unready takes operator SSH and mosh off 192.168.55.226 — "
        "while gating no endpoint of its own, since gbrain declares no ports"
    )
    # And the point only holds while the Service really is Ready-gated.
    svc = _load(MANIFESTS / "service.yaml")
    assert svc["spec"].get("publishNotReadyAddresses") is not True, (
        "service.yaml has grown publishNotReadyAddresses=true — that changes the "
        "premise of the probe decision above (and of the `ssh` readinessProbe "
        "the runbook relies on); re-derive both before leaving this green"
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

    Three checks, because names and paths are only the surface. The one that
    actually matters is the last: two volumes with different NAMES mounted at
    different PATHS can still name the SAME `claimName`, which is one RWO
    Longhorn volume with two Postgres instances on it. Nothing about that edit
    looks like a coupling — it is a one-word change in a field neither of the
    other two assertions reads.
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

    gbrain_claims, hindsight_claims = _claim_names(gbrain), _claim_names(hindsight)
    assert gbrain_claims, "gbrain must mount at least one PVC (its own store)"
    assert hindsight_claims, "hindsight must mount at least one PVC (its own store)"
    shared_claims = gbrain_claims & hindsight_claims
    assert not shared_claims, (
        f"gbrain and hindsight must resolve to DISJOINT PVCs, found "
        f"{sorted(shared_claims)}. Distinct volume names and distinct mountPaths "
        "prove nothing on their own — pointing both at one claimName puts two "
        "Postgres instances on a single RWO volume, which is exactly the "
        "coupling #759's revision was written to prevent"
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
        "changes NOTHING about the ssh container. Its image pin is moved by the "
        "scheduled agent-images bump workflow, not by this branch (that bump is "
        "how the Bun runtime arrived; see the re-pin manual operation)"
    )


def test_gbrain_does_not_override_the_image_entrypoint():
    """No `command:`. Everything this container does correctly, the stock
    `docker-entrypoint.sh` does — and a `command:` replaces it silently.

    Three things would be lost at once, none of them visible in a diff that
    merely adds a plausible-looking `command: ["postgres", ...]`:

      * `initdb` never runs, so a fresh volume never becomes a database;
      * `/docker-entrypoint-initdb.d` is never read, so `CREATE EXTENSION vector`
        never happens and the ConfigMap becomes decorative;
      * `chmod 00700 "$PGDATA"` never runs. That chmod is in
        `docker_create_db_directories`, which the entrypoint calls on EVERY start
        (before the "already initialised" branch), and it is what puts a
        populated PGDATA back to 0700 after a kubelet `fsGroup` re-walk has
        loosened it — reproduced 2026-08-03 on this exact digest. It is the same
        boot-time hook the `hermes-agent-shell-hindsight` image hand-rolls; here
        it comes free, and only from the entrypoint.

    `args:` (the `-c` server flags) is the supported way to configure this image:
    the entrypoint prepends `postgres` itself when the first arg starts with `-`.
    """
    gbrain = _gbrain()

    assert "command" not in gbrain, (
        "gbrain must NOT declare a `command:` — that replaces the image's "
        "docker-entrypoint.sh, which is what runs initdb, reads "
        f"{INITDB_DIR}, and chmods PGDATA back to 0700 on every start. Server "
        "configuration belongs in `args:`; the entrypoint prepends `postgres` "
        "when the first arg starts with `-`"
    )


def test_gbrain_startup_probe_allows_time_for_initdb():
    """The startup budget is deliberate, and asserted rather than left in a
    comment.

    First boot runs `initdb` on a freshly-provisioned Longhorn volume before
    anything can answer `pg_isready`. A tight budget — `failureThreshold: 1`, or
    a short period — kills the container MID-INITDB, and the kubelet then
    restarts it onto a half-written PGDATA, which is a worse state than either
    failing or succeeding cleanly. The manifest and the spec both call the 150 s
    generous on purpose; nothing enforced it until the 2026-08-03 review.

    Only the startup probe carries this budget. Readiness and liveness run
    against an already-initialised database and are deliberately tighter.
    """
    startup = _gbrain()["startupProbe"]
    period = startup["periodSeconds"]
    threshold = startup["failureThreshold"]

    assert threshold > 1, (
        f"startupProbe.failureThreshold is {threshold} — a single failed probe "
        "would kill the container during initdb on first boot"
    )
    assert period * threshold >= 150, (
        f"the startup budget is {period}s x {threshold} = {period * threshold}s, "
        "below the 150s the manifest and spec both state deliberately. First boot "
        "runs initdb on a fresh Longhorn volume before pg_isready can answer, and "
        "a container killed mid-initdb restarts onto a half-written PGDATA"
    )


def test_gbrain_declares_no_container_port():
    """No `ports:` entry. Declaring a containerPort for a loopback-only server
    advertises reachability that does not exist — the same reason the Hindsight
    sidecar declares none for 5433."""
    assert not _gbrain().get("ports"), (
        "gbrain must declare NO containerPort — nothing off-pod can reach 5434, "
        "and a declared port would claim otherwise"
    )
