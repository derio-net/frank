"""Evaluate the upgrade-session admission policies for real (p4-r3, p4-r7, p5-r1).

Runs the CEL in apps/cluster-update-fr/manifests/admission-policy.yaml against the console's REAL
pod shapes (scripts/tests/fixtures/life/podspec/<type>.json, byte copies of the console's golden
testdata/podspec/<type>.json, built by launch.go podSpec) and against hostile variants. Needs cel-python,
which does not build on every interpreter; without it the tests skip and the phase-7 manual
check `life-admission-dry-run` is the evidence instead.
"""
import copy
import json
import os
import re
from pathlib import Path

import pytest
import yaml

try:
    import celpy
except ImportError:  # cel-python does not build on Python 3.14 (the local venv); CI runs 3.12
    if os.environ.get("CI") == "true":
        raise RuntimeError("cel-python is missing in CI: the admission policies would go unevaluated "
                           "(install the dev group: uv sync --group dev)")
    pytest.skip("cel-python not installed (it does not build on this interpreter); CI evaluates "
                "these, and manual op life-admission-dry-run checks them server-side", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[2]
DOCS = [d for d in yaml.safe_load_all((ROOT / "apps/cluster-update-fr/manifests/admission-policy.yaml").read_text()) if d]
POLICIES = {d["metadata"]["name"]: d for d in DOCS if d["kind"] == "ValidatingAdmissionPolicy"}
CONSOLE = "system:serviceaccount:cluster-update-fr:cluster-update-fr"
IMAGE = "ghcr.io/derio-net/upgrade-session:3f2a9c1"
TYPES = ["chart-major", "stateful", "rollouts", "frank-os", "hop-os"]
PODS = ROOT / "scripts/tests/fixtures/life/podspec"
_env = celpy.Environment()


def _tailscale_pin():
    var = next(v for v in POLICIES["upgrade-session-pods"]["spec"]["variables"] if v["name"] == "tailscaleImage")
    return re.fullmatch(r"'([^']+)'", var["expression"]).group(1)


TAILSCALE = _tailscale_pin()


def console_pod(typ):
    """The console's own pod for `typ`, with the configured images (SESSION_IMAGE and
    SESSION_TAILSCALE_IMAGE are console config, the fixture carries placeholders)."""
    p = json.loads((PODS / f"{typ}.json").read_text())
    for c in p["spec"].get("initContainers", []):
        c["image"] = TAILSCALE
    return p


def _cel(v):
    # celpy.json_to_cel turns Python bools into ints, which breaks `!` and `&&`; convert by hand.
    t = celpy.celtypes
    if isinstance(v, bool):
        return t.BoolType(v)
    if isinstance(v, dict):
        return t.MapType({t.StringType(k): _cel(x) for k, x in v.items()})
    if isinstance(v, (list, tuple)):
        return t.ListType([_cel(x) for x in v])
    if isinstance(v, str):
        return t.StringType(v)
    if isinstance(v, int):
        return t.IntType(v)
    return v


def _split(s, sep):
    # Kubernetes CEL's ext.strings split (Go strings.Split): "a  b".split(" ") keeps the empty
    # token, as Python's str.split(sep) does. cel-python ships no strings extension.
    return celpy.celtypes.ListType([celpy.celtypes.StringType(x) for x in str(s).split(str(sep))])


def _eval(expr, activation):
    prog = _env.program(_env.compile(expr), functions={"split": _split})
    return prog.evaluate({k: _cel(v) for k, v in activation.items()})


def decide(policy, obj, user=CONSOLE, groups=(), name="", namespace="upgrade-sessions", operation="CREATE"):
    """(allowed, failed messages) the way the API server applies matchConditions + validations."""
    spec = POLICIES[policy]["spec"]
    act = {"object": obj, "request": {"userInfo": {"username": user, "groups": list(groups)},
                                      "name": name, "namespace": namespace, "operation": operation}}
    for c in spec.get("matchConditions", []):
        if not bool(_eval(c["expression"], act)):
            return True, []
    variables = {}
    for v in spec.get("variables", []):
        variables[v["name"]] = _eval(v["expression"], {**act, "variables": variables})
    failed = []
    for v in spec["validations"]:
        try:
            ok = bool(_eval(v["expression"], {**act, "variables": variables}))
        except celpy.CELEvalError:
            # The API server denies on an evaluation error under failurePolicy Fail. cel-python also
            # raises where real CEL would not (it rewrites bools to ints inside macros over nested
            # maps), so an error counts as a denial here, and the legitimate pods above prove the
            # expressions do not raise on valid input.
            ok = False
        if not ok:
            failed.append(v["message"])
    return not failed, failed


def pod(typ="stateful", **over):
    p = console_pod(typ)
    for path, val in over.items():
        node = p
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = val
    return p


@pytest.mark.parametrize("typ", TYPES)
def test_the_consoles_own_pod_shape_is_admitted_for_every_type(typ):
    assert decide("upgrade-session-pods", console_pod(typ)) == (True, [])


def test_the_tailscale_pin_is_a_digest():
    assert re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", TAILSCALE)


def _hop(mutate):
    p = console_pod("hop-os")
    mutate(p)
    return p


def _ts(p):
    return p["spec"]["initContainers"][0]


def _session(p):
    return p["spec"]["containers"][0]


def _envvar(c, name):
    return next(e for e in c["env"] if e["name"] == name)


def _authkey(p):
    return next(e for e in _ts(p)["env"] if e["name"] == "TS_AUTHKEY")


HOP_HOSTILE = {
    "second init container": lambda p: p["spec"]["initContainers"].append(dict(_ts(p), name="tailscale2")),
    "no init container": lambda p: p["spec"].pop("initContainers"),
    "init renamed": lambda p: _ts(p).update(name="helper"),
    "init not a native sidecar": lambda p: _ts(p).pop("restartPolicy"),
    "tailscale by tag": lambda p: _ts(p).update(image="tailscale/tailscale:v1.82.5"),
    "tailscale other digest": lambda p: _ts(p).update(image="tailscale/tailscale@sha256:" + "f" * 64),
    "session image as sidecar": lambda p: _ts(p).update(image=IMAGE),
    "sidecar as root": lambda p: _ts(p)["securityContext"].update(runAsUser=0),
    "sidecar uid unset": lambda p: _ts(p)["securityContext"].pop("runAsUser"),
    "sidecar mounts the agent credentials": lambda p: _ts(p)["volumeMounts"].append(
        {"name": "credentials", "mountPath": "/c"}),
    "sidecar mounts home": lambda p: _ts(p)["volumeMounts"].append({"name": "home", "mountPath": "/h"}),
    "sidecar envFrom": lambda p: _ts(p).update(envFrom=[{"secretRef": {"name": p["metadata"]["name"] + "-creds"}}]),
    "sidecar command": lambda p: _ts(p).update(command=["sh"]),
    "sidecar args": lambda p: _ts(p).update(args=["-c", "x"]),
    "sidecar unknown env": lambda p: _ts(p)["env"].append({"name": "TS_ROUTES", "value": "0.0.0.0/0"}),
    "socks5 off loopback": lambda p: _envvar(_ts(p), "TS_SOCKS5_SERVER").update(value="0.0.0.0:1055"),
    "http proxy off loopback": lambda p: _envvar(_ts(p), "TS_OUTBOUND_HTTP_PROXY_LISTEN").update(value=":1056"),
    "scanner's tag": lambda p: _envvar(_ts(p), "TS_EXTRA_ARGS").update(
        value=_envvar(_ts(p), "TS_EXTRA_ARGS")["value"].replace("tag:frank-session", "tag:frank-updater")),
    # security review of the sidecar rule: argv is tokenized and allowlisted, every TS_* var
    # appears exactly once (Kubernetes uses the LAST duplicate), and the binds are exact.
    "smuggled flag": lambda p: _envvar(_ts(p), "TS_EXTRA_ARGS").update(
        value=_envvar(_ts(p), "TS_EXTRA_ARGS")["value"] + " --exit-node=100.64.0.1"),
    "smuggled flag glued to the tag": lambda p: _envvar(_ts(p), "TS_EXTRA_ARGS").update(
        value=_envvar(_ts(p), "TS_EXTRA_ARGS")["value"].replace(
            "--advertise-tags=tag:frank-session", "--advertise-tags=tag:frank-session --accept-routes")),
    "empty token": lambda p: _envvar(_ts(p), "TS_EXTRA_ARGS").update(
        value=_envvar(_ts(p), "TS_EXTRA_ARGS")["value"].replace(" ", "  ", 1)),
    "required token missing": lambda p: _envvar(_ts(p), "TS_EXTRA_ARGS").update(
        value=" ".join(t for t in _envvar(_ts(p), "TS_EXTRA_ARGS")["value"].split() if not t.startswith("--login-server"))),
    "required token twice": lambda p: _envvar(_ts(p), "TS_EXTRA_ARGS").update(
        value=_envvar(_ts(p), "TS_EXTRA_ARGS")["value"] + " --advertise-tags=tag:frank-session"),
    "another session's hostname": lambda p: _envvar(_ts(p), "TS_EXTRA_ARGS").update(
        value=_envvar(_ts(p), "TS_EXTRA_ARGS")["value"].replace("--hostname=frank-upgrade-", "--hostname=frank-upgrade-x")),
    "duplicate TS_EXTRA_ARGS, good then bad": lambda p: _ts(p)["env"].append(
        {"name": "TS_EXTRA_ARGS", "value": "--login-server=https://evil.example --advertise-tags=tag:frank-updater"}),
    "duplicate authkey": lambda p: _ts(p)["env"].append(copy.deepcopy(_authkey(p))),
    "duplicate socks5": lambda p: _ts(p)["env"].append({"name": "TS_SOCKS5_SERVER", "value": "localhost:1055"}),
    "http proxy on 0.0.0.0:1056": lambda p: _envvar(_ts(p), "TS_OUTBOUND_HTTP_PROXY_LISTEN").update(value="0.0.0.0:1056"),
    "socks5 on another loopback port": lambda p: _envvar(_ts(p), "TS_SOCKS5_SERVER").update(value="localhost:9999"),
    "kernel networking": lambda p: _envvar(_ts(p), "TS_USERSPACE").update(value="false"),
    "state elsewhere": lambda p: _envvar(_ts(p), "TS_STATE_DIR").update(value="/tmp"),
    "kube secret state": lambda p: _envvar(_ts(p), "TS_KUBE_SECRET").update(value="tailscale"),
    "extra tag": lambda p: _envvar(_ts(p), "TS_EXTRA_ARGS").update(
        value=_envvar(_ts(p), "TS_EXTRA_ARGS")["value"].replace("tag:frank-session", "tag:frank-session,tag:hop-node")),
    "authkey from another secret": lambda p: _authkey(p)["valueFrom"]["secretKeyRef"].update(name="us-other-creds"),
    "authkey is another key": lambda p: _authkey(p)["valueFrom"]["secretKeyRef"].update(key="github-token"),
    "sidecar reads another key": lambda p: _ts(p)["env"].append({"name": "X", "valueFrom": {"secretKeyRef": {
        "name": p["metadata"]["name"] + "-creds", "key": "hop-talosconfig"}}}),
    "session mounts ts-state": lambda p: _session(p)["volumeMounts"].append({"name": "ts-state", "mountPath": "/s"}),
    "session reads the authkey": lambda p: _session(p)["env"].append({"name": "K", "valueFrom": {"secretKeyRef": {
        "name": p["metadata"]["name"] + "-creds", "key": "tailscale-authkey"}}}),
    "session envFrom": lambda p: _session(p).update(envFrom=[{"secretRef": {"name": p["metadata"]["name"] + "-creds"}}]),
    "creds volume projects the authkey": lambda p: next(v for v in p["spec"]["volumes"] if v["name"] == "credentials")[
        "secret"]["items"].append({"key": "tailscale-authkey", "path": "k"}),
    "creds volume without items": lambda p: next(v for v in p["spec"]["volumes"] if v["name"] == "credentials")[
        "secret"].pop("items"),
}


@pytest.mark.parametrize("why", sorted(HOP_HOSTILE))
def test_hostile_hop_os_sidecars_are_denied(why):
    allowed, failed = decide("upgrade-session-pods", _hop(HOP_HOSTILE[why]))
    assert not allowed and failed, why


@pytest.mark.parametrize("typ", [t for t in TYPES if t != "hop-os"])
def test_only_hop_os_carries_the_tailscale_sidecar(typ):
    p = console_pod(typ)
    p["spec"]["initContainers"] = copy.deepcopy(console_pod("hop-os")["spec"]["initContainers"])
    assert not decide("upgrade-session-pods", p)[0]


def test_a_digest_pinned_session_image_is_admitted():
    p = pod(**{"spec.containers": [{"name": "s", "image": "ghcr.io/derio-net/upgrade-session@sha256:" + "a" * 64}]})
    assert decide("upgrade-session-pods", p)[0]


HOSTILE = {
    "wrong image": pod(**{"spec.containers": [{"name": "s", "image": "docker.io/library/alpine:3.20"}]}),
    "look-alike image": pod(**{"spec.containers": [{"name": "s", "image": "ghcr.io/derio-net/upgrade-session-evil:1"}]}),
    "wrong init image": pod(**{"spec.initContainers": [{"name": "i", "image": "busybox:1.37.0"}]}),
    "other service account": pod(**{"spec.serviceAccountName": "upgrade-session-rollouts"}),
    "default SA for an in-cluster type": pod(**{"spec.serviceAccountName": "default"}),
    "privileged SA outside the set": pod(**{"spec.serviceAccountName": "argocd-server"}),
    "hostPath": pod(**{"spec.volumes": [{"name": "h", "hostPath": {"path": "/"}}]}),
    "privileged": pod(**{"spec.containers": [{"name": "s", "image": IMAGE, "securityContext": {"privileged": True}}]}),
    "added capability": pod(**{"spec.containers": [{"name": "s", "image": IMAGE, "securityContext": {"capabilities": {"add": ["SYS_ADMIN"]}}}]}),
    "hostNetwork": pod(**{"spec.hostNetwork": True}),
    "hostPID": pod(**{"spec.hostPID": True}),
    "ephemeral container": pod(**{"spec.ephemeralContainers": [{"name": "dbg", "image": IMAGE}]}),
    "missing managed-by": pod(**{"metadata.labels": {"cluster-update.fr/type": "stateful"}}),
    "unknown type": pod(**{"metadata.labels": {"cluster-update.fr/type": "root", "app.kubernetes.io/managed-by": "cluster-update-fr"}}),
    "token on stateful off": pod(**{"spec.automountServiceAccountToken": False}),
    # p5-session-selection-explicit: command replaces the entrypoint that selects the clients.
    "command overrides the entrypoint": pod(**{"spec.containers": [{"name": "s", "image": IMAGE, "command": ["bash"]}]}),
}


@pytest.mark.parametrize("why", sorted(HOSTILE))
def test_hostile_pods_are_denied(why):
    allowed, failed = decide("upgrade-session-pods", HOSTILE[why])
    assert not allowed and failed, why


def test_hop_os_with_a_token_or_an_sa_is_denied():
    assert not decide("upgrade-session-pods", pod("hop-os", **{"spec.automountServiceAccountToken": True}))[0]
    assert not decide("upgrade-session-pods", pod("hop-os", **{"spec.serviceAccountName": "upgrade-session-stateful"}))[0]


def test_other_users_are_not_this_policys_business():
    assert decide("upgrade-session-pods", HOSTILE["wrong image"], user="system:serviceaccount:kube-system:x")[0]


# --- secrets (p4-r3)


def secret(**over):
    s = {"type": "Opaque", "metadata": {"name": "us-abc-1-creds", "labels": {"app.kubernetes.io/managed-by": "cluster-update-fr"},
                                       "annotations": {"cluster-update.fr/owner": "abc"}}}
    for path, val in over.items():
        node = s
        keys = path.split(".")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = val
    return s


def test_the_consoles_own_secrets_are_admitted():
    assert decide("upgrade-session-secrets", secret()) == (True, [])


@pytest.mark.parametrize("why,obj", [
    ("service-account-token type", secret(type="kubernetes.io/service-account-token")),
    ("sa annotation", secret(**{"metadata.annotations": {"kubernetes.io/service-account.name": "upgrade-session-stateful"}})),
    ("wrong prefix", secret(**{"metadata.name": "argocd-secret"})),
    ("no managed-by", secret(**{"metadata.labels": {}})),
    ("dockerconfig type", secret(type="kubernetes.io/dockerconfigjson")),
])
def test_hostile_secrets_are_denied(why, obj):
    assert not decide("upgrade-session-secrets", obj)[0], why


# --- ephemeral containers


def test_ephemeral_containers_need_a_cluster_admin():
    assert not decide("upgrade-session-no-ephemeral-containers", {}, user="alice", groups=["root-devops"])[0]
    assert not decide("upgrade-session-no-ephemeral-containers", {}, user=CONSOLE)[0]
    assert decide("upgrade-session-no-ephemeral-containers", {}, user="op", groups=["root-admins"])[0]
    assert decide("upgrade-session-no-ephemeral-containers", {}, user="x", groups=["system:masters"])[0]


# --- exec / attach / port-forward (p5-r10)
RUNS_FR = "system:serviceaccount:runs-fr:runs-fr"


def _admin_subjects():
    """Every subject the repo binds to admin / edit / cluster-admin: RBAC lets each of them exec
    into a session pod, so the admission policy is what stops them."""
    out = []
    for f in list((ROOT / "apps").rglob("*.yaml")) + list((ROOT / "clusters/hop/apps").rglob("*.yaml")):
        if "/vendor/" in str(f) or "/chart/" in str(f):
            continue
        try:
            docs = list(yaml.safe_load_all(f.read_text()))
        except yaml.YAMLError:
            continue
        for d in docs:
            if isinstance(d, dict) and d.get("kind") in ("RoleBinding", "ClusterRoleBinding") and \
                    (d.get("roleRef") or {}).get("name") in ("admin", "edit", "cluster-admin") and \
                    (d["kind"] == "ClusterRoleBinding" or d["metadata"].get("namespace") == "upgrade-sessions"):
                out += d.get("subjects", [])
    return out


def _identity(subject):
    if subject["kind"] == "ServiceAccount":
        return (f"system:serviceaccount:{subject['namespace']}:{subject['name']}",
                ["system:serviceaccounts", f"system:serviceaccounts:{subject['namespace']}", "system:authenticated"])
    if subject["kind"] == "Group":
        return "someone@derio.net", [subject["name"], "system:authenticated"]
    return subject["name"], ["system:authenticated"]


def test_the_repo_binds_these_admin_subjects():
    got = {(s["kind"], s.get("namespace"), s["name"]) for s in _admin_subjects()}
    assert got == {("Group", None, "root-admins"), ("Group", None, "root-devops"), ("Group", None, "root-agents"),
                   ("ServiceAccount", "secure-agent-pod", "agent-sa")}, "a new admin binding: decide its exec rights"


@pytest.mark.parametrize("subject", _admin_subjects(), ids=lambda s: s["name"])
def test_only_cluster_admins_proper_may_exec_into_a_session(subject):
    user, groups = _identity(subject)
    allowed = decide("upgrade-session-no-exec", {}, user=user, groups=groups)[0]
    assert allowed == (subject["kind"] == "Group" and subject["name"] == "root-admins"), subject


def test_exec_policy_also_covers_pods_proxy():
    rule = POLICIES["upgrade-session-no-exec"]["spec"]["matchConstraints"]["resourceRules"][0]
    assert "pods/proxy" in rule["resources"]


def test_runs_fr_and_system_masters_may_exec_and_the_console_may_not():
    assert decide("upgrade-session-no-exec", {}, user=RUNS_FR, groups=["system:serviceaccounts"])[0]
    assert decide("upgrade-session-no-exec", {}, user="kubernetes-admin", groups=["system:masters"])[0]
    assert not decide("upgrade-session-no-exec", {}, user=CONSOLE)[0]
    assert not decide("upgrade-session-no-exec", {}, user="system:serviceaccount:runs-fr-staging:runs-fr")[0]
    assert not decide("upgrade-session-no-exec", {}, user="alice", groups=["runs-fr"])[0]


# --- trust model (p5-trust-model): tokens for the session and runs-fr ServiceAccounts
NODE = ("system:node:gpu-1", ["system:nodes", "system:authenticated"])
SESSION_SAS = ["upgrade-session-" + t for t in TYPES if t != "hop-os"]


def token_request(kind="Pod"):
    spec = {"audiences": ["https://kubernetes.default.svc"], "expirationSeconds": 3607}
    if kind:
        spec["boundObjectRef"] = {"apiVersion": "v1", "kind": kind, "name": "us-x-1", "uid": "u"}
    return {"apiVersion": "authentication.k8s.io/v1", "kind": "TokenRequest", "spec": spec}


GUARDED_SAS = [(sa, "upgrade-sessions") for sa in SESSION_SAS] + [("runs-fr", "runs-fr")]


@pytest.mark.parametrize("sa,ns", GUARDED_SAS)
def test_only_the_kubelet_mints_tokens_for_session_and_runs_fr_sas(sa, ns):
    # the kubelet's projected token for the pod it runs (NodeRestriction pins the pod to its node)
    assert decide("upgrade-session-sa-tokens", token_request(), user=NODE[0], groups=NODE[1], name=sa, namespace=ns)[0]
    # ...but not a free-standing token, even from a node identity
    assert not decide("upgrade-session-sa-tokens", token_request(kind=None), user=NODE[0], groups=NODE[1],
                      name=sa, namespace=ns)[0]
    assert not decide("upgrade-session-sa-tokens", token_request(kind="Secret"), user=NODE[0], groups=NODE[1],
                      name=sa, namespace=ns)[0]
    for user, groups in (("alice", ["root-devops"]), ("system:serviceaccount:secure-agent-pod:agent-sa", ["system:serviceaccounts"]),
                         (CONSOLE, ["system:serviceaccounts"]), ("system:node-imposter", ["system:authenticated"]),
                         ("system:node:gpu-1", ["system:authenticated"])):
        assert not decide("upgrade-session-sa-tokens", token_request(), user=user, groups=groups, name=sa, namespace=ns)[0], user
    for groups in (["root-admins"], ["system:masters"]):
        assert decide("upgrade-session-sa-tokens", token_request(kind=None), user="op", groups=groups, name=sa, namespace=ns)[0]


def test_other_service_accounts_are_not_the_token_policys_business():
    assert decide("upgrade-session-sa-tokens", token_request(kind=None), user="alice", name="default", namespace="upgrade-sessions")[0]
    assert decide("upgrade-session-sa-tokens", token_request(kind=None), user="alice", name="other", namespace="runs-fr")[0]
    assert decide("upgrade-session-sa-tokens", token_request(kind=None), user="alice", name="runs-fr", namespace="elsewhere")[0]


RS_CONTROLLER = "system:serviceaccount:kube-system:replicaset-controller"


def runs_fr_pod(sa="runs-fr"):
    return {"metadata": {"name": "runs-fr-abc"}, "spec": {"serviceAccountName": sa, "containers": [{"name": "c", "image": "x"}]}}


@pytest.mark.parametrize("op", ["CREATE", "UPDATE"])
def test_only_the_replicaset_controller_runs_pods_as_runs_fr(op):
    d = lambda pod, user, groups=(): decide("runs-fr-pods", pod, user=user, groups=groups, namespace="runs-fr", operation=op)[0]
    assert d(runs_fr_pod(), RS_CONTROLLER, ["system:serviceaccounts"])
    assert d(runs_fr_pod(), "op", ["root-admins"]) and d(runs_fr_pod(), "op", ["system:masters"])
    for user, groups in (("alice", ["root-devops"]), ("system:serviceaccount:argocd:argocd-application-controller", []),
                         ("system:serviceaccount:secure-agent-pod:agent-sa", []), ("system:node:gpu-1", ["system:nodes"])):
        assert not d(runs_fr_pod(), user, groups), user
    assert d(runs_fr_pod("default"), "alice", ["root-devops"]), "another SA is not this policy's business"

