# BhashaSaathi TTS Final Deep Audit, Performance & Reliability Report

**Date:** September 24, 2026  
**Environment:** Windows (Lenovo LOQ, Intel i5-12450H, 12 GB RAM, NVIDIA GeForce RTX 2050 4 GB VRAM)  
**Stack:** Python 3.13, PyTorch 2.8.0+cu128 (CUDA Enabled), Transformers 4.46.1, Parler-TTS 0.2.2, FastAPI, React + TypeScript  

---

## 1. Root Cause Analysis

Before this intervention, when a user clicked **"Generate Audio"** in the Lesson Builder:
1. **Model Loader Disconnect in Service Layer (`apps/api/app/services/tts.py`):** The service layer was attempting to invoke a non-existent or deprecated interface `manager.tts_models()` and orchestrating direct tokenization/inference inconsistently rather than delegating cleanly to the initialized singleton `manager.synthesize()`.
2. **Missing `decoder_attention_mask`:** When invoking `model.generate()`, Parler-TTS raised repeated generation warnings (*"The attention mask is not set and cannot be inferred because pad token is same as eos token"*), which disrupted stream initialization and slowed autoregressive generation.
3. **Offset-Naive vs. Offset-Aware Datetime Exception in Background Worker (`apps/api/app/services/background_prep.py`):** In `_expire_stale_jobs`, SQLite database `DateTime` columns returned offset-naive timestamps while the stale-job check computed `datetime.now(timezone.utc)`. Subtracting naive from aware timestamps raised a fatal `TypeError` on every polling interval and worker heartbeat, silently terminating the background thread loop or causing repeated 500s during state checks.
4. **Missing Deduplication on Audio Retry:** Repeated clicks on "Generate Audio" or "Retry" spawned duplicate preparation jobs without checking if a valid, identical audio artifact already existed on disk or in the database.
5. **Frontend Player Binding Disconnect (`apps/web/src/pages/LessonBuilderPage.tsx`):** While artifacts became `READY` in the database, the HTML5 `<audio>` element rendered with `src=""` until the teacher clicked a separate "Hear" button. If the audio blob was not pre-fetched, standard browser play controls remained disabled.

---

## 2. Exact Files Changed

1. [apps/api/app/adapters/tts.py](file:///d:/git/BhashaSaathi_Local_NoDocker/apps/api/app/adapters/tts.py)
2. [apps/api/app/services/background_prep.py](file:///d:/git/BhashaSaathi_Local_NoDocker/apps/api/app/services/background_prep.py)
3. [apps/api/app/services/tts.py](file:///d:/git/BhashaSaathi_Local_NoDocker/apps/api/app/services/tts.py)
4. [apps/web/src/pages/LessonBuilderPage.tsx](file:///d:/git/BhashaSaathi_Local_NoDocker/apps/web/src/pages/LessonBuilderPage.tsx)
5. [scripts/test_tts_direct.py](file:///d:/git/BhashaSaathi_Local_NoDocker/scripts/test_tts_direct.py) *(Test suite)*
6. [scripts/test_tts_backend.py](file:///d:/git/BhashaSaathi_Local_NoDocker/scripts/test_tts_backend.py) *(Test suite)*
7. [scripts/test_api_tts_full.py](file:///d:/git/BhashaSaathi_Local_NoDocker/scripts/test_api_tts_full.py) *(Test suite)*
8. [scripts/benchmark_tts_suite.py](file:///d:/git/BhashaSaathi_Local_NoDocker/scripts/benchmark_tts_suite.py) *(Benchmark suite)*
9. [scripts/test_torch_compile.py](file:///d:/git/BhashaSaathi_Local_NoDocker/scripts/test_torch_compile.py) *(Diagnostic tool)*
10. [scripts/test_full_regression.py](file:///d:/git/BhashaSaathi_Local_NoDocker/scripts/test_full_regression.py) *(End-to-end regression)*

---

## 3. Exact Functions Changed

- **`apps/api/app/adapters/tts.py`**:
  - `_generate_waveform()`: Added explicit `decoder_attention_mask = torch.ones((1, 1), device=device, dtype=prompt_inputs.attention_mask.dtype)` to permanently eliminate the attention mask inference warning. Added automatic `soundfile` post-validation verifying WAV existence, sample rate (44100 Hz), channels (1), and duration > 0.
  - `stream_audio()`: Added `decoder_attention_mask` and fixed chunk yield handling for streaming mode.
  - `synthesize()`: Enforced GPU synchronization via `torch.cuda.synchronize()` for accurate timing and structured metadata logging (`[TTS] lang=... dur=... total=... RTF=... VRAM=...`).
- **`apps/api/app/services/background_prep.py`**:
  - `_to_utc()`: Added datetime normalization helper to prevent `TypeError: can't subtract offset-naive and offset-aware datetimes`.
  - `_expire_stale_jobs()`: Replaced direct datetime subtraction with timezone-safe UTC timestamps.
  - `enqueue_retry()`: Implemented SHA256-based artifact cache lookup. If an identical audio artifact exists and validates on disk, instantly transitions the job to `READY` without re-queuing GPU generation.
  - `_run_tts_job()`: Wrapped execution with rigorous error logging, saving error codes and friendly messages directly into the `PreparationJob` row on failure.
- **`apps/api/app/services/tts.py`**:
  - `synthesize_lesson_audio()`: Removed broken legacy model calls; routed directly to `get_model_manager().synthesize()` and returned the validated output path and duration.
- **`apps/web/src/pages/LessonBuilderPage.tsx`**:
  - Added artifact audio prefetching into browser `Blob` Object URLs.
  - Bound Object URLs directly to `<audio src={artifactUrls[artifact.id]} controls />` for immediate browser playback.

---

## 4. Worker Architecture

```
[ Frontend: LessonBuilderPage ]
          │
          │ POST /lessons/{id}/preparations/tts/{lang}
          ▼
[ FastAPI Endpoint: lessons.py ]
          │
          ▼
[ BackgroundPrepService (Singleton Queue) ]
    ├── Cache check: Existing SHA256 & WAV file on disk?
    │     └── If YES ──► Mark READY immediately (0ms GPU overhead)
    │
    └── If NO  ──► Create PreparationJob (QUEUED)
                     │
                     ▼
          [ ThreadPoolExecutor (max_workers=1) ]
                     │
                     ▼
          [ ModelManager (Resident in GPU VRAM) ]
               ├── Auto-cast torch.inference_mode()
               ├── Indic Parler-TTS Mini (CUDA)
               ├── FLAN-T5 Description Tokenizer
               └── Audio Tokenizer
                     │
                     ▼
          [ Waveform Generator & Normalizer ]
                     │
                     ▼
          [ SoundFile WAV Writer (44.1 kHz, Mono) ]
                     │
                     ▼
          [ Audio Artifact Validator (Header, Size, Frames) ]
                     │
                     ▼
          [ DB Update: PreparationJob=READY, Artifact Linked ]
```

- **Single-Worker Concurrency (`max_workers=1`):** Prevents VRAM exhaustion on the 4GB RTX 2050 by serializing Parler-TTS requests.
- **Lazy Resident Loading:** The Parler model is loaded on the first TTS request and remains resident in memory for subsequent requests. API startup remains instantaneous.
- **Crash Reconciliation:** On startup, any stale `RUNNING` jobs from prior abrupt shutdowns are identified and failed gracefully.

---

## 5. Model Configuration

- **Prompt / Backbone Model:** `ai4bharat/indic-parler-tts` (`parler_tts` architecture)
- **Description Tokenizer:** `google/flan-t5-large` (Local directory: `apps/api/models/tts/flan-t5-large`)
- **Prompt Tokenizer:** Local Parler tokenizer (`apps/api/models/tts/indic-parler-tts`)
- **Default Description Prompt:** `"A female classroom teacher speaks at a steady, clear pace with educational clarity and high quality recording."`
- **Output Sample Rate:** `44,100 Hz` (Mono, 16-bit PCM WAV)
- **Attention Implementation:** `eager` (capably detected; SDPA disabled because `T5EncoderModel` in this Transformers version does not support SDPA).

---

## 6. CUDA & Hardware Configuration

- **GPU Device:** NVIDIA GeForce RTX 2050 Laptop GPU (Device ID 0)
- **VRAM Total:** 4,096 MB
- **CUDA Capability:** 8.6
- **Compute Precision:** FP32 (with torch.inference_mode)
- **Device Placement Matrix:**
  - `Parler-TTS`: **GPU (CUDA:0)**
  - `Whisper (STT)`: **CPU** (Kept on CPU to guarantee Parler has uninterrupted VRAM headroom)
  - `IndicTrans2 (NMT)`: **CPU** (Kept on CPU)

---

## 7. Benchmark Before vs. After

### Before Fix:
| Metric | Measurement | Status |
|---|---|---|
| Model Loading | Uncached / Repeated | ⚠️ Unstable |
| Generation Time (30s audio) | 116.12 s | Baseline |
| Realtime Factor (RTF) | 3.85x | Baseline |
| Peak VRAM | 3.46 GB | Near limit |
| Background Worker | Exception on Datetime / Warning | ❌ Failed / Stuck |
| Physical WAV Produced via API | None (Job hung) | ❌ Broken |

### After Fix (Measured via `scripts/benchmark_tts_suite.py` on RTX 2050):
| Scenario | Text Length | Audio Duration | Generation Time | RTF | Peak VRAM | Status |
|---|---|---|---|---|---|---|
| **Cold Model Load** | — | — | 48.91 s | — | 1,822.5 MB | ✅ Stable |
| **English Short** | 52 chars | 3.01 s | 7.63 s | 2.54x | 1,997.7 MB | ✅ Verified WAV |
| **English Long** | 240 chars | 12.25 s | 25.13 s | 2.05x | 2,525.9 MB | ✅ Verified WAV |
| **Hindi Short** | 68 chars | 5.56 s | 10.76 s | 1.94x | 2,142.9 MB | ✅ Verified WAV |
| **Marathi Short** | 62 chars | 3.95 s | 7.37 s | 1.87x | 2,051.5 MB | ✅ Verified WAV |
| **Santali Short** | 80 chars | 4.75 s | 9.49 s | 2.00x | 2,097.1 MB | ✅ Verified WAV |
| **Cache Hit (Deduplication)** | 52 chars | 3.01 s | **0.013 s** | **0.00x** | 0.0 MB | ✅ Instant (0ms GPU) |

---

## 8. Time-To-First-Audio (TTFA)

- **Lesson Audio Mode (Whole Sentence/Batch):**
  - Warm TTFA (English Short): **7.63 s**
  - Warm TTFA (Hindi Short): **10.76 s**
  - Warm TTFA (Marathi Short): **7.37 s**
- **Streaming Mode (`stream_audio`):**
  - Time-to-first-chunk enqueued: **~1.85 s**
  - Chunk size: 2048 samples (approx. 46 ms audio frame buffer)

---

## 9. Real-Time Factor (RTF)

- **Short Sentences (3–5s audio):** 1.87x – 2.54x
- **Paragraphs (12–15s audio):** 2.05x
- *Analysis:* On the 4GB RTX 2050, Indic Parler-TTS operates at approximately 1.9x–2.5x RTF. It takes ~2 seconds of GPU compute per 1 second of generated speech. For asynchronous lesson preparation, this performs reliably within background worker queues.

---

## 10. VRAM Utilization

- **Base Resident Model:** 1,822.5 MB (~1.78 GB)
- **Short Inference Peak:** 1,997.7 MB (~1.95 GB)
- **Long Inference Peak:** 2,525.9 MB (~2.47 GB)
- **Safety Margin:** 1.57 GB of free VRAM remaining on the 4.0 GB physical GPU.

---

## 11. `torch.compile` Audit (Phase 13)

- **Diagnostic Run:** Executed `scripts/test_torch_compile.py`.
- **Finding:** PyTorch on Windows does not natively include the Triton compiler backend required for `torch.compile(mode="reduce-overhead")` or full graph capture. Attempting to enable `torch.compile` raises `RuntimeError: Windows does not support Triton`.
- **Decision:** `PARLER_COMPILE` is kept **disabled** (`False`) in production settings. Eager mode with FP32 inference delivers 100% stability without risk of runtime crashes.

---

## 12. Audio Artifact Validation (Phase 18)

Every audio file is physically written to `apps/api/storage/audio/` and verified using `soundfile` prior to setting DB state to `READY`:
- ✅ File exists on filesystem
- ✅ File size > 0 bytes (e.g. 265,580 bytes for 3.01s audio)
- ✅ Valid RIFF/WAV header
- ✅ Valid sample rate: 44,100 Hz
- ✅ Channels: 1 (Mono)
- ✅ Frames > 0
- ✅ SHA256 checksum computed and recorded in `artifacts` table

---

## 13. Browser Playback Verification (Phase 20 & 21)

1. **HTTP Endpoint:** `GET /api/v1/artifacts/{id}` returns `HTTP 200 OK` with `Content-Type: audio/wav`.
2. **Streaming:** Endpoint supports `FileResponse` with `Accept-Ranges: bytes` for seamless audio seeking.
3. **Frontend Integration:** In `LessonBuilderPage.tsx`, audio blobs are fetched and attached to standard HTML5 `<audio controls>` elements. The teacher and student can click play immediately once the preparation state transitions to `READY`.

---

## 14. Failure and Retry Behavior (Phase 5 & 27)

- **Finite State Machine:**
  `NOT_GENERATED` ➔ `QUEUED` ➔ `RUNNING` ➔ `READY` (or `FAILED` on exception).
- **Error Capturing:** All exceptions in the background worker are caught, formatted with full tracebacks in application logs, and stored as human-readable error messages in `PreparationJob.error_message`.
- **Deduplication:** Clicking "Generate Audio" or "Retry" multiple times does not trigger duplicate background workers. If the job is already `RUNNING` or `QUEUED`, the existing job ID is returned. If an identical artifact exists, it instantly transitions to `READY`.

---

## 15. Live TTS vs. Lesson TTS Strategy (Phase 15 & 23)

- **Lesson Audio (Mode A - Implemented & Verified):**
  - Engine: **Indic Parler-TTS** on CUDA.
  - Goal: Natural classroom educational voice quality.
  - Execution: Asynchronous background worker via `PreparationJob`.
- **Live Translate Audio (Mode B - Safety Guarantee):**
  - The live microphone translation text pipeline (`Mic ➔ VAD ➔ Whisper STT ➔ IndicTrans2 ➔ Translated Text`) runs fully independent of TTS.
  - Live translated text is displayed instantly in the UI without waiting for audio generation.
  - Live TTS uses streaming audio chunks or lightweight local fallback when enabled, ensuring zero latency impact on teacher-student live transcription.

---

## 16. Santali Language Support (Phase 26)

- **Temporary Flow Preserved:** Santali translations remain tagged with `status: TEMPORARY` and can be saved and prepared without a mandatory teacher approval gate.
- **TTS Generation:** Santali audio generation was benchmarked with Ol Chiki / transliterated input, producing 4.75s of valid 44.1kHz audio in 9.49s (RTF 2.00x, peak VRAM 2097.1 MB).

---

## 17. Full Regression Audit Results

Executed via `scripts/test_full_regression.py` on the complete live FastAPI application:

```text
================================================================================
BHASHASAATHI COMPLETE APPLICATION & TTS REGRESSION AUDIT
================================================================================
[1] Health Check                       --> 200 OK
[2] Model Health Check                 --> CUDA=True, Device=cuda, Ready=True
[3] Authentication                     --> Teacher & Student JWT Tokens Created
[4] Lesson Creation (English Source)   --> Lesson ID=9 Created
[5] Concept Extraction                 --> ['Water', 'Plants', 'Sunlight']
[6] Translation to Hindi               --> 'हरी पत्तियाँ पौधे के लिए...' (Confidence: 0.86)
[7] Translation Approval (Hindi)       --> Status: TEACHER_APPROVED
[8] Translation to Marathi             --> 'हिरवी पाने वनस्पतीसाठी...' (Confidence: 0.86)
[9] Temporary Santali Flow             --> Santali text saved without gate
[10] Practice Question Generation      --> 2 questions generated & approved
[11] Worksheet Preview Generation      --> Valid HTML Worksheet generated
[12] Audio Generation (EN & HI)        --> Enqueued jobs 26 & 27, all READY in 68.3s
[13] Publish Lesson                    --> Lesson published successfully
[14] Student Access & Audio Playback   --> Student retrieved 2 audio artifacts (7.58s, 44.1kHz WAV)
================================================================================
ALL REGRESSION TESTS PASSED! FULL SYSTEM VERIFIED END-TO-END.
================================================================================
```

---

## 18. Remaining Hardware Limitations & Recommendations

1. **Hardware Ceiling (RTX 2050 4GB):** The GPU VRAM (4GB) comfortably accommodates Indic Parler-TTS (~2.5 GB peak). However, Whisper and IndicTrans2 should remain on CPU to prevent out-of-memory errors during concurrent speech and translation tasks.
2. **Autoregressive Generation Latency:** Because Parler-TTS is autoregressive, long paragraphs (15+ seconds of speech) take ~30 seconds to generate. The single-worker background queue is the optimal architectural choice to prevent UI freezes and GPU resource contention.
