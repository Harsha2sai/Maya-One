# Baseline Snapshot (Pre-Chaos)

**Snapshot Date**: 2026-02-12  
**Purpose**: Frozen baseline for controlled chaos experiments

## System State

### Dependencies
- **Requirements Hash**: `cbd2016b317bfba1be5ee37ffd1ef657`
- **Git Commit**: `291ef3bdfa80c2ff4bbddfb7d5312788f244a17c`

### Model Versions
- **LLM**: `groq/llama-3.3-70b-versatile`
- **STT**: `deepgram/nova-2`
- **TTS**: `elevenlabs/eleven_turbo_v2_5`

### Verification Baseline
- **Probe Suite**: 13/13 passing
- **Categories**: Tools (3), Memory (2), Modes (2), Conversation (2), Failures (4)

### Telemetry Baseline (P50/P95/P99)

| Metric | Median | P95 | P99 |
|--------|--------|-----|-----|
| `tokens_in` | 1189 | 7066 | 7238 |
| `tokens_out` | 205 | 723 | 882 |
| `context_size` | 1298 | 7493 | 7972 |
| `llm_latency` | 2.05s | 4.64s | 5.67s |
| `stream_first_chunk_latency` | 0.65s | 1.98s | 2.36s |

### Refined Thresholds
- **Context Tokens**: 8500 (warn) / 12000 (critical)
- **LLM Latency**: 5.0s (warn) / 8.0s (critical)
- **First Chunk Latency**: 2.5s (warn) / 4.5s (critical)
- **Retries**: 1 (warn) / 3 (critical)
- **Memory Retrieval**: 2 (warn) / 5 (critical)

## Safety Architecture Status

### Layer 1: Boot Gate ✅
- 6 startup checks (LLM, STT, TTS, Memory, Tools, Schemas)

### Layer 2: Runtime Probes ✅
- StreamProbe with 3s timeout guard

### Layer 3: Verification Suite ✅
- 13 comprehensive tests

### Layer 4: Telemetry ✅
- 9 metrics tracked
- Experiment tagging enabled
- Recovery detection (3-turn threshold)
- Cost guardrails active

## Chaos Readiness

### Guardrails Configured
- **Token Budget**: 50,000 per session
- **Retry Limit**: 5 per request
- **Session Duration**: 300s max
- **Consecutive Failures**: 10 max

### Recovery Metrics
- **Detection**: 3 consecutive healthy turns
- **Tracking**: `system_recovery_turns` metric

---

**This baseline is frozen. No code changes until chaos testing completes.**
