Plan for the speech service (#1006). Phase 1: sharing config, VRAM budget guard and gpu-switcher groups. Phase 2: the speech app, private exposure, alerts and benchmark harness. Phase 3 (manual): live rollout, benchmark run and follow-up issues. # manual-operation blocks are authored in phase 2 task 5.


## Manual operations

These four operations are the only non-declarative steps of the speech service. `infer-speech-gpu-switcher-image` and `infer-speech-image-build` are PRE-MERGE (the Deployments pin images that must already exist in GHCR); `infer-speech-device-plugin-roll` is POST-MERGE; `infer-speech-benchmark-run` follows it and produces the numbers that replace the `estimate: true` VRAM sizes.

```yaml
# manual-operation
id: infer-speech-gpu-switcher-image
layer: infer
app: gpu-switcher
plan: docs/superpowers/plans/2026-11-16--infer--speech-service
when: "BEFORE the PR merges — the gpu-switcher Deployment pins ghcr.io/derio-net/gpu-switcher:v0.1.2 (group support), which must exist in GHCR first."
why_manual: "The gpu-switcher image has no CI workflow (it is built by hand on the Intel MacBook; Frank has no build host), and a first push to GHCR creates the package private."
commands: |
  cd apps/gpu-switcher/app
  docker buildx build --platform linux/amd64 -t ghcr.io/derio-net/gpu-switcher:v0.1.2 --push .
  # If the package is private: GitHub -> derio-net -> Packages -> gpu-switcher -> Package settings -> Change visibility -> Public
verify: |
  docker manifest inspect ghcr.io/derio-net/gpu-switcher:v0.1.2 >/dev/null && echo present
  # anonymous pull works (no imagePullSecret on Frank):
  docker logout ghcr.io; docker pull ghcr.io/derio-net/gpu-switcher:v0.1.2
status: pending
```

```yaml
# manual-operation
id: infer-speech-image-build
layer: infer
app: speech
plan: docs/superpowers/plans/2026-11-16--infer--speech-service
when: "BEFORE the PR merges — the speech Deployment pins ghcr.io/derio-net/speech:<SPEECH_REV> (the derived speaches image with CTranslate2 >= 4.6.3). CI builds it only on a push to main, and workflow_dispatch needs the workflow on the default branch, so the first image is built locally."
why_manual: "workflow_dispatch cannot run a workflow that is not yet on the default branch, so the pre-merge image is built and pushed from the Intel MacBook (Frank has no build host); a first GHCR push creates the package PRIVATE, so making it public is a manual UI step (Frank pulls anonymously)."
commands: |
  REV=$(grep -o 'SPEECH_REV: "[^"]*"' .github/workflows/build-speech.yml | cut -d'"' -f2)
  CT2=$(grep -o 'CTRANSLATE2_VERSION: "[^"]*"' .github/workflows/build-speech.yml | cut -d'"' -f2)
  echo "$GITHUB_TOKEN_OR_PAT" | docker login ghcr.io -u <github-user> --password-stdin   # a PAT with write:packages
  docker buildx build --platform linux/amd64 --build-arg CTRANSLATE2_VERSION=$CT2 -t ghcr.io/derio-net/speech:$REV --push apps/speech/docker
  # GitHub -> derio-net -> Packages -> speech -> Package settings -> Change visibility -> Public
verify: |
  REV=$(grep -o 'SPEECH_REV: "[^"]*"' .github/workflows/build-speech.yml | cut -d'"' -f2)
  docker logout ghcr.io; docker manifest inspect ghcr.io/derio-net/speech:$REV >/dev/null && echo "public + present"
status: pending
```

```yaml
# manual-operation
id: infer-speech-device-plugin-roll
layer: infer
app: gpu-operator
plan: docs/superpowers/plans/2026-11-16--infer--speech-service
when: "After the PR merges — BEFORE scaling the speech Deployment up. Order matters: sync gpu-operator-extras first (it creates the time-slicing-config ConfigMap), confirm the ConfigMap exists, and only then sync gpu-operator (whose devicePlugin.config references it)."
why_manual: "The device plugin must start with the sharing config, and gpu-1 only advertises 2 nvidia.com/gpu after it does. A ClusterPolicy change makes the gpu-operator ROLL the plugin pods (a restart, not a live reload), which briefly drops the node's GPU resource and can disturb running GPU pods — do it while no GPU workload is mid-job. Syncing gpu-operator before the ConfigMap exists would roll the plugin onto a missing config."
commands: |
  source .env
  argocd app sync gpu-operator-extras --port-forward --port-forward-namespace argocd
  kubectl -n gpu-operator get configmap time-slicing-config   # must exist BEFORE the next step
  argocd app sync gpu-operator --port-forward --port-forward-namespace argocd
  kubectl -n gpu-operator rollout status daemonset/nvidia-device-plugin-daemonset --timeout=300s
  # If the plugin pod's start time predates the ConfigMap/ClusterPolicy change, roll it by hand:
  #   kubectl -n gpu-operator rollout restart daemonset/nvidia-device-plugin-daemonset
  # Rollback: revert the devicePlugin.config reference in apps/gpu-operator/values.yaml (or set replicas: 1 in the ConfigMap),
  # let ArgoCD sync and the plugin roll again. Scale speech to 0 first so nothing holds the second slot.
verify: |
  kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}{"\n"}'   # 2
  kubectl -n gpu-operator logs daemonset/nvidia-device-plugin-daemonset --tail=20 | grep -i "replicas\|sharing"
  kubectl -n ollama get pods   # check whether the running holder restarted during the roll"
status: pending
```

```yaml
# manual-operation
id: infer-speech-benchmark-run
layer: infer
app: speech
plan: docs/superpowers/plans/2026-11-16--infer--speech-service
when: "After infer-speech-device-plugin-roll, with speech scaled up beside the allowlisted Ollama model (activate the group through gpu-switcher). Needs operator-supplied samples/en.wav, samples/de.wav, samples/el.wav (16-bit PCM WAV, a minute or two each; keep them short because speech.cluster.derio.net is subject to the edge's default read timeout)."
why_manual: "Needs the live GPU, the loaded Ollama model, operator-supplied audio and listening judgement on Greek/German TTS quality; results decide the Greek/German TTS engine and replace the estimate: true VRAM sizes."
commands: |
  source .env
  W=$(mktemp -d)   # private scratch dir for the logs and audio (no fixed /tmp paths)
  # Start the group: gpu-switcher activates ollama + speech together.
  kubectl -n speech rollout status deploy/speech --timeout=600s
  SMI_POD=$(kubectl -n gpu-operator get pod -l app=nvidia-device-plugin-daemonset --field-selector spec.nodeName=gpu-1 -o jsonpath='{.items[0].metadata.name}')
  SMI="nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -l 1"
  # 1. Baseline (whole card): Ollama loaded, speech idle. Wait > 300 s after the last speech request so STT/TTS models have unloaded.
  kubectl -n gpu-operator exec "$SMI_POD" -- timeout 60 $SMI > "$W/smi-base.csv"
  # 2. Run: the in-pod `timeout` ends the sampler, so there is nothing to kill.
  kubectl -n gpu-operator exec "$SMI_POD" -- timeout 1800 $SMI > "$W/smi-run.csv" &
  SAMPLER=$!
  python3 scripts/speech-benchmark/run.py --base-url https://speech.cluster.derio.net \
    --stt-model deepdml/faster-whisper-large-v3-turbo-ct2 --samples-dir samples --out-dir "$W/tts-audio" \
    --tts EN=speaches-ai/Kokoro-82M-v1.0-ONNX:af_heart --tts DE=speaches-ai/Kokoro-82M-v1.0-ONNX:af_heart --tts EL=speaches-ai/Kokoro-82M-v1.0-ONNX:af_heart \
    --baseline-smi-log "$W/smi-base.csv" --nvidia-smi-log "$W/smi-run.csv" --out docs/investigations/2026-11-16--infer--speech-benchmark.md
  kubectl -n gpu-operator exec "$SMI_POD" -- pkill -f 'nvidia-smi --query-gpu' ; wait $SAMPLER || true
  # Listen to "$W"/tts-audio/tts-{en,de,el}.mp3, pick the Greek/German TTS engine, re-run with other --tts if needed.
  # Then edit apps/speech/manifests/files/vram-budget.yaml with the SPEECH-ONLY figure (peak - baseline, estimate: false) and record
  # the Greek/German TTS engine decision in the spec/journal.
verify: |
  test -s docs/investigations/2026-11-16--infer--speech-benchmark.md && grep -c '^| \(stt\|tts\) ' docs/investigations/2026-11-16--infer--speech-benchmark.md
  grep 'Speech-only VRAM' docs/investigations/2026-11-16--infer--speech-benchmark.md   # a number, not n/a
status: pending
```
