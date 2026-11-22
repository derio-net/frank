# Speech service benchmark on gpu-1 (#1006)

**Run:** 2026-11-22 ~17:06 local, Test Plan step 7, manual-op `infer-speech-benchmark-run`
(wrapped by `scripts/tmp/speech-benchmark.sh`, which drives `scripts/speech-benchmark/run.py`).
**Card:** RTX 5070 Ti, 16 GB, driver 570.211.01 (CUDA 12.8), time-sliced x2.
**Speech image:** `ghcr.io/derio-net/speech:0.9.0-rc.3-ct2-4.6.3-r2` (CTranslate2 4.6.3, no CUDA compat libcuda, frank#1017).
**Beside it:** Ollama with `gemma4:12b-64k` loaded, 100% GPU, 8.5 GB (the VRAM budget's allowlisted model).
**Inputs:** about 28 s of read speech per language (en, de, el), recorded live on the operator's Mac. The recordings are not committed.

## Results

| kind | lang | model | total s | metric | value | state |
|------|------|-------|---------|--------|-------|-------|
| stt | en | deepdml/faster-whisper-large-v3-turbo-ct2 | 41.559 | rtf | 1.486 | **cold**: first call after the model unloaded |
| stt | de | deepdml/faster-whisper-large-v3-turbo-ct2 | 0.615 | rtf | 0.022 | warm |
| stt | el | deepdml/faster-whisper-large-v3-turbo-ct2 | 0.750 | rtf | 0.026 | warm |
| tts | en | speaches-ai/Kokoro-82M-v1.0-ONNX | 8.423 | ttfa_s | 8.411 | **cold** |
| tts | de | speaches-ai/piper-de_DE-thorsten-high | 4.053 | ttfa_s | 3.989 | **cold** |
| tts | el | speaches-ai/piper-el_GR-rapunzelina-low | 1.146 | ttfa_s | 1.093 | cold (small model) |

| VRAM (nvidia-smi, whole card) | MiB |
|---|---|
| Baseline (Ollama loaded, speech idle) | 8822 |
| Peak during the run (all speech models loaded) | 11757 |
| **Speech-only (peak - baseline)** | **2935** |

## Reading the numbers

- **Cold rows measure model loading, not inference.** The wrapper waits 330 s before the baseline, so speech unloads its models (`STT_MODEL_TTL=300`). The first STT call (en) therefore paid Whisper's load plus CUDA initialisation, about 40 s. Each TTS model's first call paid its own load. Warm STT runs at **rtf 0.02–0.03, about 40x real time**. Warm TTS time to first byte was 0.10–0.24 s in the same day's listening tests (Test Plan step 3).
- **Batch transcription** is warm after the first seconds, so a 2 h 25 min recording should take roughly 3–4 minutes of GPU time at rtf 0.025. That estimate is extrapolated, not measured. The retired whisper.cpp script needed about 6 minutes. A long run is Test Plan step 5's job.
- **Real-time voice (push-to-talk) is dominated by the cold start.** After 5 idle minutes, the first utterance waits about 40 s for STT and several seconds for TTS. Keeping the models resident costs the measured 2.9 GB, which fits: 11.8 GB of 16 GB peak, with the allowlisted Ollama model loaded. The streaming / real-time follow-up should either raise `STT_MODEL_TTL` (and the TTS equivalent) or keep the models warm, with that 2.9 GB in the budget.
- **VRAM.** Speech-only use (2.9 GB, all four speech models loaded) is well under the budget's per-model estimates (2.5 + 1.5 + 0.4 + 0.2 = 4.6 GB). `vram-budget.yaml` records the measured total next to them. The run measures the models only together, so the per-model figures stay estimates.

## TTS quality (operator listening, Test Plan steps 3 and 7)

- English, Kokoro `af_heart`: natural.
- German, Piper `thorsten-high`: natural and steady.
- Greek, Piper `rapunzelina-low`: natural and steady. It is the only Greek Piper voice.
- Kokoro has no German or Greek voice: German came out with an English accent, and Greek was spelled letter by letter.

Decision recorded in the spec journal as `tts-engine-per-language-1`. Stronger multilingual engines (XTTS-v2 / F5-TTS class) remain an option for a later comparison, mainly for voice quality and voice cloning.
