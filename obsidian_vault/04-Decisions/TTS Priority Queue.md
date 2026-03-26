# Decision: TTS Priority Queue System

## Context
- TTS (Text-to-Speech) responses competing for audio pipeline
- Voice responses experiencing latency and instability
- No predictability in TTS execution order
- Voice pipeline need for stability improvements

## Decision
**Phase 7 Implementation:**
- Implement TTS priority queue system for voice stability
- Queue system manages TTS execution order
- Priority: system messages > user requests > background tasks

## Reasoning
- Better observability across all audio layers
- Voice pipeline stability improvements
- Predictable TTS execution order
- Better debugging capabilities
- Reduces race conditions in audio pipeline

## Tradeoffs
**Benefits:**
- ✅ Voice pipeline stability
- ✅ Predictable TTS execution
- ✅ Better observability
- ✅ Race condition prevention

**Costs:**
- ⚠️ Additional queue management overhead
- ⚠️ Requires careful priority assignment
- ⚠️ May delay non-critical TTS slightly

## Impacted Components
- [[Audio Session Manager]] (`core/audio/audio_session_manager.py`)
- [[Resilient TTS]] (`core/providers/resilient_tts.py`)
- [[AgentOrchestrator]] (message prioritization)

## Related
- [[Trace Propagation]]
- [[Phase Architecture]] Phase 7
- [[Voice Pipeline]] Phase 5
