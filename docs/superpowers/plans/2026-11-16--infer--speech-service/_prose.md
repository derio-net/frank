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
when: "BEFORE the PR merges — the speech Deployment pins ghcr.io/derio-net/speech:<SPEECH_REV> (the derived speaches image with CTranslate2 >= 4.6.3), which CI only builds on a push to main touching apps/speech/docker/**."
why_manual: "The first build must run from the feature branch before merge, or the merge would roll out an ImagePullBackOff; and a first GHCR push creates the package PRIVATE, so making it public is a manual UI step (Frank pulls anonymously)."
commands: |
  gh workflow run build-speech.yml --ref <feature-branch>
  gh run watch "$(gh run list --workflow build-speech.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
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
when: "After the PR merges and ArgoCD has synced gpu-operator-extras (time-slicing-config ConfigMap) and gpu-operator (devicePlugin.config) — BEFORE scaling the speech Deployment up."
why_manual: "The NVIDIA device plugin reads its sharing config at start-up and is not restarted by a ConfigMap change; until it rolls, gpu-1 still advertises 1 nvidia.com/gpu and a speech pod beside Ollama stays Pending. The roll briefly re-registers the node's GPU resource, so do it while no GPU workload is mid-job."
commands: |
  source .env
  # Ordering: the ConfigMap must exist before the plugin that references it restarts.
  kubectl -n gpu-operator get configmap time-slicing-config
  kubectl -n gpu-operator rollout restart daemonset/nvidia-device-plugin-daemonset
  kubectl -n gpu-operator rollout status daemonset/nvidia-device-plugin-daemonset --timeout=300s
  # Rollback: revert the devicePlugin.config reference in apps/gpu-operator/values.yaml (or set replicas: 1 in the ConfigMap),
  # let ArgoCD sync, then repeat the rollout restart above. Scale speech to 0 first so nothing holds the second slot.
verify: |
  kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}{"\n"}'   # 2
  kubectl -n gpu-operator logs daemonset/nvidia-device-plugin-daemonset --tail=20 | grep -i "replicas\|sharing"
  kubectl -n ollama get pods   # the running holder was not disturbed
status: pending
```

```yaml
# manual-operation
id: infer-speech-benchmark-run
layer: infer
app: speech
plan: docs/superpowers/plans/2026-11-16--infer--speech-service
when: "After infer-speech-device-plugin-roll, with speech scaled up beside the allowlisted Ollama model (activate the group through gpu-switcher)."
why_manual: "Needs the live GPU, the loaded Ollama model and listening judgement on Greek/German TTS quality; results decide the Greek/German TTS engine and replace the estimate: true VRAM sizes."
commands: |
  source .env
  # Start the group: gpu-switcher activates ollama + speech together.
  kubectl -n speech rollout status deploy/speech --timeout=600s
  # Sample VRAM on gpu-1 while the benchmark runs (second shell / background):
  kubectl -n gpu-operator exec ds/nvidia-device-plugin-daemonset -- nvidia-smi --query-gpu=memory.used --format=csv -l 1 > /tmp/speech-smi.csv &
  python3 scripts/speech-benchmark/run.py --base-url https://speech.cluster.derio.net \
    --stt-model deepdml/faster-whisper-large-v3-turbo-ct2 --tts-model speaches-ai/Kokoro-82M-v1.0-ONNX --voice af_heart \
    --audio en=samples/en.wav de=samples/de.wav el=samples/el.wav \
    --nvidia-smi-log /tmp/speech-smi.csv --out docs/investigations/2026-11--infer--speech-benchmark.md
  kill %1
  # Then: edit apps/speech/manifests/files/vram-budget.yaml with the measured peak (estimate: false) and record the
  # Greek/German TTS engine decision in the spec/journal.
verify: |
  test -s docs/investigations/2026-11--infer--speech-benchmark.md && grep -c '^| \(stt\|tts\) ' docs/investigations/2026-11--infer--speech-benchmark.md
  grep 'Peak VRAM' docs/investigations/2026-11--infer--speech-benchmark.md   # a number, not n/a
status: pending
```
