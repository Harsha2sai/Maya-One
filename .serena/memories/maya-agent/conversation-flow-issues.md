# Maya Agent Conversation Flow Issues - Analysis & Solution

## Date: 2026-04-08

## Issues Identified

### 1. **End-of-Utterance (EOU) Detection Problems**
**Symptom:** Agent searches before user finishes talking; conversation feels choppy

**Root Cause:**
- `MIN_ENDPOINTING_DELAY` defaults to 1.5s in `agent.py:_resolve_endpointing_delays()`
- This is too aggressive for natural speech patterns where users pause mid-thought
- The agent treats mid-sentence pauses as turn completion

**Fix Required:**
```python
# In _resolve_endpointing_delays()
min_endpointing_delay = 2.5  # Was 1.5s - too aggressive
max_endpointing_delay = 5.0  # Allow longer for complex thoughts
```

### 2. **Conversation Context Loss**
**Symptom:** Agent says "This conversation just started" even after multiple exchanges

**Root Cause:**
- Session-scoped conversation history not properly maintained in voice mode
- `conversation_summary` is not being passed consistently to `classify_with_context()`
- Voice pipeline uses different context path than text channel

**Fix Required:**
- Ensure `_append_conversation_history()` is called for all voice turns
- Pass `conversation_summary` to router and classifier consistently
- Use session_key based storage for voice sessions

### 3. **Pronoun/Anaphora Resolution Failure**
**Symptom:** "Who is the PM of India?" → "Tell me more about him" → "I don't know who 'he' is"

**Root Cause:**
- `ResearchHandler.resolve_research_subject_from_context()` exists but:
  1. Session key generation is inconsistent between storage and retrieval
  2. `_RESEARCH_PRONOUN_TOKENS` detection works but subject extraction fails
  3. `PronounRewriter.rewrite()` is not being invoked before query processing

**Fix Required:**
- Fix session key consistency (use participant.identity or room.name)
- Ensure `PronounRewriter` runs before research handler in the pipeline
- Add proper entity extraction from research results

### 4. **Shallow Response Synthesis**
**Symptom:** Responses are bullet points without depth; doesn't build on conversation

**Root Cause:**
- `ResultSynthesizer.synthesize()` uses brief mode by default
- No conversation context passed to synthesis
- Research results published directly without conversational framing

**Fix Required:**
- Change default voice_mode to "deep" for research
- Pass conversation context to synthesizer
- Add follow-up detection to expand on previous answers

## Implementation Priority

1. **EOU Timing** (Quick win) - Environment variable change
2. **Context Loss** (High impact) - Session management fix
3. **Pronoun Resolution** (Medium) - Pipeline ordering fix
4. **Response Depth** (Polish) - Synthesizer enhancement

## Key Files to Modify

- `Agent/agent.py` - EOU timing, session initialization
- `Agent/core/orchestrator/agent_orchestrator.py` - Context persistence
- `Agent/core/orchestrator/research_handler.py` - Session key fix
- `Agent/core/research/result_synthesizer.py` - Response depth
- `Agent/config/settings.py` - Add conversation context settings