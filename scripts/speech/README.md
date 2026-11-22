# Speech service operator checks

Helpers for walking the speech service (`apps/speech`, #1006) live on gpu-1. They were written for the DevOps-gate Test Plan of the 2026-11-16 speech service run (spec: `docs/superpowers/implemented/specs/2026-11-16--infer--speech-service-design.md`), and they are reusable for any later change to speech, gpu-switcher or the GPU sharing.

Every script except the benchmark prints a **one-line, colon-free gate answer** at the end, ready for `fr ops gate`'s `ran … / owed …` prompt.

| Script | Checks | Needs |
|---|---|---|
| `speech-stt-check.sh` | Records a short clip per language (en, de, el) and POSTs it without a language hint. Passes when the auto-detected language matches. | mic, `ffmpeg` |
| `speech-tts-check.sh` | Synthesizes a sentence per language (Kokoro `af_heart` for en, Piper `thorsten` for de, Piper `rapunzelina` for el) and plays it, then asks you to judge each one. `--kokoro-only` repeats the old Kokoro-for-everything comparison. | `afplay` |
| `speech-batch-alerts-check.sh` | Batch-transcribes a long recording **in-cluster**, optionally cycles the GPU to ComfyUI and back (`--cycle-comfyui`), then reads Grafana's alert history: no related alert may fire. `--record MINUTES` records the sample first. | `kubectl`, mic or a file |
| `speech-exposure-check.sh` | Read-only: the route serves speaches on the LAN (body checked, not just DNS), public DNS returns NXDOMAIN (with a DNS-over-HTTPS fallback), and the Hop edge does not serve it. | `dig`, the repo's `.env_hop` |
| `speech-benchmark.sh` | Wraps `scripts/speech-benchmark/run.py`: loads the allowlisted Ollama model, takes a whole-card VRAM baseline, then measures STT speed factor, TTS time to first audio and speech-only VRAM. | `kubectl`, mic or samples |

Run them from a frank checkout. They find the repo's `.talos/Frank_Kubeconfig.yaml` and `.env_hop` themselves. Both files are gitignored, so from an fr worktree the scripts look in the main checkout. Most need to be on the LAN or mesh, with speech up: activate `ollama` in gpu-switcher, which starts the `ollama` group, speech included. Output (audio, transcripts, reports) goes to `~/Downloads/speech-*-<time>/` and never into the repo, because the recordings are your voice.

## Things these checks learned the hard way

- **Long recordings use the in-cluster service.** `speech.cluster.derio.net` is subject to the websecure entrypoint's read timeout, so `speech-batch-alerts-check.sh` streams the audio through `kubectl exec` into the pod (`127.0.0.1:8000`).
- **Grafana must be running the merged rules.** It reads its alert-rule files only at boot. The batch check refuses to run until the live rules match git (a preflight). Otherwise a passing alert check proves nothing; see #1026.
- **Pending is not firing.** The Layer 11 and Layer 16 `gpu_timeshare` rules flip by design whenever the other workload holds the card. They only update the health-bridge tile, and they are listed as by-design. The speech rule and `gpu-node-both-down` always count.
- **Cold versus warm.** After 5 idle minutes the models unload (`STT_MODEL_TTL=300`). The first call afterwards pays model load: about 40 s for STT, 1–8 s for TTS. Warm STT runs about 40× real time. The benchmark's idle wait makes its first rows cold on purpose.
- **Name resolution proves nothing on the LAN.** `*.cluster.derio.net` is a wildcard to Traefik. The exposure check asserts on speaches' own response body and runs a negative control.
