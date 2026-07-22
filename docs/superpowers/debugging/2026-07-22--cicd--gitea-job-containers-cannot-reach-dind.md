# Gitea job containers can't reach the DinD daemon (or its published ports)

**Date:** 2026-07-22
**Layer:** cicd
**Fix:** `apps/gitea-runner/manifests/config.yaml` (`container.network` + `container.options`)
**Guard:** `scripts/tests/test_gitea_runner_app.py::test_job_containers_can_reach_the_docker_daemon`

## Symptom & reproduction

Exposed by the `CI_AUTHORITY` cutover the same day (see
`2026-07-22--cicd--gitea-skipped-status-stranded-on-github.md` and manual op
`cicd-stoa-ci-authority-cutover`): once Gitea became the sole CI authority,
every workflow job that shells out to the `docker` CLI failed within ~5s.

`cnc-fru` `ci / smoke`, Gitea run 20 job 255:

```
ERROR: failed to connect to the docker API at unix:///var/run/docker.sock;
       check if the path is correct and if the daemon is running:
       dial unix /var/run/docker.sock: connect: no such file or directory
   ❌  Failure - Main docker build -t cnc-fru:smoke .
exitcode '1': failure
```

Reproduce: push to any mirror whose workflow runs `docker …` in a `run:` step.

## Evidence

**Blast radius** — of the 14 workflows across the 5 mirrors, the docker-CLI
users are `cnc-fr` (`acceptance-report.yml`, `compose-smoke.yml`), `cnc-frd`
(`ci.yml`, 6 invocations) and `cnc-fru` (`ci.yml`, 4). `second-brain` and
`hermes-brain` use none — which is exactly why `second-brain#18` went 3/3
green and the migration's 2026-07-20 "smoke-proven" note held: that proof ran
on one of the two repos with no docker usage.

**Topology.** `apps/gitea-runner` runs `act_runner` + a privileged
`docker:dind` sidecar in one pod. DinD serves plain TCP on `:2375` and the
runner reaches it at `tcp://localhost:2375` (they share the pod netns). But a
*job* is a container created **on** that daemon — a sibling, not the host.

**act_runner does not bridge the gap for a TCP host.** From its own
`generate-config` output:

> `docker_host` — overrides the docker client host with the specified one. …
> If it's `"-"`, act_runner will find an available docker host automatically,
> but **the docker host won't be mounted to the job containers** …

The mounting path is for unix sockets. With `docker_host: tcp://…` there is
nothing to mount and no `DOCKER_HOST` is injected, so the job's CLI falls back
to the default `unix:///var/run/docker.sock`, which does not exist in it.

**Measured directly against the live daemon** (containers on a bridge network
vs. the host network, with a published-port probe running):

```
bridge  daemon localhost:2375 FAIL   published port localhost:18088 FAIL
host    daemon localhost:2375 OK     published port localhost:18088 OK
```

## Root cause

**Job containers are siblings of the DinD daemon rather than sharing its host,
so both affordances a GitHub-hosted runner provides for free are absent** —
the daemon endpoint (no socket, and act_runner won't propagate a TCP
`docker_host`) and the published-port namespace (`-p 8088:80` lands on the
DinD host, so the job's own `curl localhost:8088` misses it).

Workflows written against GitHub-hosted runners depend on both. `cnc-fru`'s
smoke job needs each in turn: `docker build`, then `docker run -p 8088:80`,
then `curl http://localhost:8088/`.

## Fix

```yaml
container:
  docker_host: "tcp://localhost:2375"
  network: "host"
  options: "-e DOCKER_HOST=tcp://localhost:2375"
```

`network: host` puts job containers in the DinD/pod netns, which fixes both
halves at once; `options` injects the `DOCKER_HOST` act_runner declines to
propagate for a TCP host.

**Trade-off, accepted deliberately:** with `capacity: 2`, two concurrent
docker-using jobs now share one port namespace, so fixed published ports
(cnc-fru's `8088`) can collide. The shared daemon already made fixed
container/network *names* collide identically (`docker network create smoke`),
so this widens an existing hazard rather than creating one. Drop capacity to 1
if it bites.

## Rejected hypotheses

- **DinD is unhealthy / crashlooping.** Ruled out — `test` (2m7s) and every
  non-docker job passed on the same daemon; the daemon answered `/_ping`
  throughout.
- **`docker_host: tcp://localhost:2375` is wrong.** Ruled out — it is correct
  *for act_runner itself*, which shares the pod netns. It just doesn't reach
  job containers.
- **`actions/checkout@v7` fails on Gitea.** Ruled out — the log shows
  `✅ Success - Post actions/checkout@v7`; the failure is the next step.
- **A missing Gitea org secret.** Ruled out — the failing step takes no
  secrets, and the error is a transport failure to the daemon.
- **Bridge networking plus `--add-host=host.docker.internal:host-gateway`.**
  Tested and *works for the daemon* (`/_ping` OK from a user-defined network
  via `172.17.0.1`), but leaves the published-port half broken, so smoke would
  still fail at its assertions. Rejected as a half-fix.
