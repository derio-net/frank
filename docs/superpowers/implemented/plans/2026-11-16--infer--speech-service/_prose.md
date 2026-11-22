Plan for the speech service (#1006). Phase 1: sharing config, VRAM budget guard and gpu-switcher groups. Phase 2: the speech app, private exposure, alerts and benchmark harness. Phase 3 (manual): live rollout, benchmark run and follow-up issues. # manual-operation blocks are authored in phase 2 task 5.


## Manual operations

These four operations are the only non-declarative steps of the speech service. All four are POST-MERGE and the DevOps stage (`fr ops gate`) runs them as fr ops. `infer-speech-gpu-switcher-image` and `infer-speech-image-build` confirm the CI-built images landed and are anonymously pullable (the Deployments ImagePullBackOff for the few minutes the builds take); `infer-speech-device-plugin-roll` follows; `infer-speech-benchmark-run` follows it and produces the numbers that replace the `estimate: true` VRAM sizes.

```yaml
# manual-operation
id: infer-speech-gpu-switcher-image
layer: infer
app: gpu-switcher
plan: docs/superpowers/plans/2026-11-16--infer--speech-service
when: "After the PR merges. .github/workflows/build-gpu-switcher.yml builds ghcr.io/derio-net/gpu-switcher:v0.1.2 (group support) on the merge push; gpu-switcher sits in ImagePullBackOff until it lands. Run by the DevOps stage as fr op postmerge-gpu-switcher-image."
why_manual: "The build itself is CI, but only the DevOps stage can confirm it landed and that the package is anonymously pullable (Frank has no imagePullSecret). The gpu-switcher package already exists publicly (v0.1.1), so no visibility change is expected."
commands: |
  fr ops apply postmerge-gpu-switcher-image --yes-mutating   # re-runs the build only if the check fails
  # by hand, from any shell with gh: gh workflow run build-gpu-switcher.yml --repo derio-net/frank --ref main
verify: |
  bash scripts/ghcr-tag-pullable.sh derio-net/gpu-switcher v0.1.2
  kubectl -n gpu-switcher rollout status deploy/gpu-switcher --timeout=300s
status: pending
```

```yaml
# manual-operation
id: infer-speech-image-build
layer: infer
app: speech
plan: docs/superpowers/plans/2026-11-16--infer--speech-service
when: "After the PR merges. .github/workflows/build-speech.yml builds ghcr.io/derio-net/speech:<SPEECH_REV> (the derived speaches image with CTranslate2 >= 4.6.3) on the merge push; the speech Deployment sits in ImagePullBackOff until it lands. Run by the DevOps stage as fr op postmerge-speech-image."
why_manual: "A FIRST push to GHCR creates the package PRIVATE and Frank pulls anonymously, so after the first green build a human must set the package public in the GitHub UI; nothing else is manual. The op's check fails until that is done, so the gate cannot pass with a private package."
commands: |
  fr ops apply postmerge-speech-image --yes-mutating   # re-runs the build only if the check fails
  # If the build is green and the check still fails: GitHub -> derio-net -> Packages -> speech -> Package settings -> Change visibility -> Public
verify: |
  REV=$(grep -o 'SPEECH_REV: "[^"]*"' .github/workflows/build-speech.yml | cut -d'"' -f2)
  bash scripts/ghcr-tag-pullable.sh derio-net/speech "$REV"
  kubectl -n speech get pods
status: pending
```

```yaml
# manual-operation
id: infer-speech-device-plugin-roll
layer: infer
app: gpu-operator
plan: docs/superpowers/plans/2026-11-16--infer--speech-service
when: "After the PR merges, BEFORE scaling the speech Deployment up, while no GPU workload is mid-job. Run by the DevOps stage as fr op postmerge-timeslice-allocatable."
why_manual: "ArgoCD cannot apply it. The gpu-operator Application ignores the ClusterPolicy's entire /spec (the operator's webhook fills in dozens of defaults), so the devicePlugin.config in apps/gpu-operator/values.yaml only takes effect on a fresh install; syncing the app changes nothing (measured 2026-11-21: Synced, live ClusterPolicy without devicePlugin.config). The op patches the live ClusterPolicy with exactly that block. A ClusterPolicy change makes the operator ROLL the device plugin, which briefly drops gpu-1's nvidia.com/gpu resource."
commands: |
  kubectl -n gpu-operator get configmap time-slicing-config   # synced by gpu-operator-extras; must exist first
  fr ops apply postmerge-timeslice-allocatable --yes-mutating
  # by hand, the same patch the op runs:
  #   kubectl patch clusterpolicy cluster-policy --type=merge -p '{"spec":{"devicePlugin":{"config":{"name":"time-slicing-config","default":"any"}}}}'
  #   kubectl -n gpu-operator rollout status daemonset/nvidia-device-plugin-daemonset --timeout=300s
  # Rollback (the op's undo): scale speech to 0 first so nothing holds the second slot, then
  #   kubectl patch clusterpolicy cluster-policy --type=json -p '[{"op":"remove","path":"/spec/devicePlugin/config"}]'
verify: |
  kubectl get clusterpolicy cluster-policy -o jsonpath='{.spec.devicePlugin.config}{"\n"}'   # {"default":"any","name":"time-slicing-config"}
  kubectl get node gpu-1 -o jsonpath='{.status.allocatable.nvidia\.com/gpu}{"\n"}'   # 2
  kubectl -n ollama get pods   # check whether the running holder restarted during the roll
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
