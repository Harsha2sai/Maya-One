# Maya Agent Conversation Flow Fix Implementation

## Overview
This document tracks the implementation of fixes for conversation flow issues in the Maya agent.

## Issues Being Fixed

### Issue 1: EOU Detection (Premature Turn Ending)
**Problem:** Agent cuts off user mid-sentence due to aggressive endpointing delay (1.5s)

**Solution:**
- Increase `MIN_ENDPOINTING_DELAY` from 1.5s to 2.5s
- Add environment variable `MAYA_ENDPOINTING_STRATEGY=conversation` for adaptive delays
- Tune based on utterance complexity

**Files Modified:**
- `Agent/agent.py` - `_resolve_endpointing_delays()` function

### Issue 2: Conversation Context Loss
**Problem:** Agent forgets previous exchanges, saying "This conversation just started"

**Solution:**
- Ensure conversation history is appended for all voice turns
- Pass `conversation_summary` to classifier and router consistently
- Fix session key consistency between voice and text paths

**Files Modified:**
- `Agent/core/orchestrator/agent_orchestrator.py` - `_append_conversation_history()` calls
- `Agent/core/routing/router.py` - Context extraction

### Issue 3: Pronoun Resolution Failure
**Problem:** "Who is he?" doesn't resolve to previously mentioned person

**Solution:**
- Fix session key generation in `ResearchHandler`
- Ensure `PronounRewriter` runs before query processing
- Improve subject extraction from research results

**Files Modified:**
- `Agent/core/orchestrator/research_handler.py` - Session key methods
- `Agent/core/orchestrator/pronoun_rewriter.py` - Integration point
- `Agent/core/orchestrator/agent_orchestrator.py` - Pipeline ordering

### Issue 4: Shallow Responses
**Problem:** Bullet-point responses without conversational depth

**Solution:**
- Change default `voice_mode` from "brief" to "deep" for research
- Pass conversation context to synthesizer
- Add conversational framing to research results

**Files Modified:**
- `Agent/core/research/result_synthesizer.py` - Response generation
- `Agent/core/orchestrator/research_handler.py` - Voice mode selection

## Implementation Status

| Issue | Status | Priority |
|-------|--------|----------|
| EOU Timing | ⏳ Pending | P0 |
| Context Loss | ⏳ Pending | P0 |
| Pronoun Resolution | ⏳ Pending | P1 |
| Response Depth | ⏳ Pending | P2 |

## Testing Plan

1. **EOU Test:** Speak "Who is the current CEO of..." (pause 2s) "OpenAI" - should not trigger search on pause
2. **Context Test:** Ask "Who is PM of India?" → "Tell me about him" → should resolve to Modi
3. **Depth Test:** Ask follow-up "What else has he done?" → should expand on previous answer

## Rollback Plan

All changes use feature flags with environment variables:
- `MAYA_ENDPOINTING_STRATEGY` - Can revert to "stt" from "conversation"
- `MAYA_CONVERSATION_CONTEXT_PERSISTENCE` - Can disable
- `MAYA_PRONOUN_REWRITE_ENABLED` - Can disable
