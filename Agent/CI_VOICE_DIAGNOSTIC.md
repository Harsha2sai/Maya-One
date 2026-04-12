# CI Voice Certification Diagnostic Script

## Current State Analysis (Run 24062813376)

### Evidence Summary
- ✅ `probe_readiness passed=true` - Agent connects and speaks greeting
- ✅ `send_message_accepted=true` - HTTP endpoint accepts messages  
- ✅ `lk.chat_sent` - Data channel message published
- ❌ `probe_ack ... source=none` - No acknowledgment from agent
- ❌ `no_user_or_agent_transcription` - Probe never receives response

### Root Cause Hypothesis

The agent receives messages but doesn't generate responses because:

1. **Voice Path (Primary)**: STT can't transcribe synthetic TTS audio
   - Deepgram rejects "robotic" audio from edge-tts
   - No `user_input_transcribed` events generated
   - Agent never receives text to process

2. **Text Path (Fallback)**: `lk.chat` messages may be filtered or ignored
   - `_accept_ingress` deduplication may reject repeated content
   - Agent may be in state where it ignores text messages
   - Orchestrator (Phase 2/3) may not be processing messages correctly

### Key Code Paths

#### 1. Voice Transcript Handling (Line 2231)
```python
def _dispatch_voice_transcript_event(...):
    if closed_event.is_set() or arch_phase < 3:
        return  # Phase 1/2 ignores voice transcripts!
```

#### 2. Text Message Handling (Line 2195-2201)
```python
if not _accept_ingress(
    origin="chat",
    sender=str(sender),
    text=text,
    source_event_id=(str(source_event_id) if source_event_id else None),
):
    return  # Message rejected by deduplication filter
```

#### 3. Message Processing (Line 2203-2214)
```python
logger.info(f"💬 [Phase {arch_phase}] lk.chat received from {sender}: {text[:120]}")
task = asyncio.create_task(
    _handle_text_chat_input(text, str(sender), participant, origin="chat", ...)
)
```

### Diagnostic Tests to Run

#### Test 1: Verify lk.chat Receipt
Add logging to confirm agent receives `lk.chat`:
```python
# In _on_data_received, before any filtering:
logger.info(f"DEBUG data_received topic={topic} sender={sender} data={data[:100]}")
```

#### Test 2: Verify _accept_ingress Result
```python
accepted = _accept_ingress(...)
logger.info(f"DEBUG _accept_ingress result={accepted} text={text[:50]}")
if not accepted:
    return
```

#### Test 3: Verify _handle_text_chat_input Entry
```python
logger.info(f"DEBUG _handle_text_chat_input called text={text[:50]}")
```

#### Test 4: Verify Response Generation
```python
logger.info(f"DEBUG response generated text={response_text[:50]}")
```

#### Test 5: Verify publish_assistant_final
```python
logger.info(f"DEBUG publish_assistant_final called turn_id={turn_id}")
```

### Fix Options

#### Option A: Force Text-Only Mode (Bypass Voice)
Skip voice audio entirely, send all probes via `lk.chat` with unique content:
```python
# In probe script, add before first probe:
for spec in probes:
    # Ensure unique content by adding timestamp
    unique_prompt = f"{spec.prompt} [{time.time()}]"
    await room.local_participant.publish_data(
        unique_prompt.encode("utf-8"),
        topic="lk.chat",
    )
```

#### Option B: Disable Deduplication for CI
Set `ingress_replay_window_s = 0` for CI runs:
```python
ingress_replay_window_s = max(
    0.0 if os.getenv("CI") == "true" else 0.2,
    float(os.getenv("VOICE_INGRESS_REPLAY_WINDOW_S", "1.25")),
)
```

#### Option C: Add Debug Endpoint
Add `/probe` endpoint that logs every step:
```python
@app.route('/probe', methods=['POST'])
async def handle_probe(request):
    text = request.json.get('message')
    logger.info(f"PROBE_RECEIVED text={text}")
    # Process through orchestrator directly
    response = await orchestrator.chat(text)
    logger.info(f"PROBE_RESPONSE text={response}")
    return web.json_response({'response': response})
```

#### Option D: Use Direct API Call Instead of LiveKit
Call the orchestrator directly via HTTP, bypassing LiveKit:
```python
# New endpoint in api/handlers.py
async def handle_chat(request):
    text = request.json.get('message')
    from core.runtime.global_agent import GlobalAgentContainer
    orchestrator = GlobalAgentContainer.get_orchestrator()
    response = await orchestrator.agent.smart_llm.chat(
        chat_ctx=[{"role": "user", "content": text}]
    )
    return web.json_response({'response': response})
```

### Recommended Fix

**Option B + Enhanced Logging** is the safest approach:

1. Disable deduplication in CI to rule out filtering
2. Add trace logging at every step
3. Run CI to identify exact failure point
4. Once identified, implement targeted fix

### Verification Steps

1. Run CI with diagnostic logging
2. Check logs for:
   - `DEBUG data_received topic=lk.chat` (message received)
   - `DEBUG _accept_ingress result=True` (not filtered)
   - `DEBUG _handle_text_chat_input called` (processing started)
   - `DEBUG response generated` (response created)
   - `DEBUG publish_assistant_final called` (response sent)

3. If all steps log but probe still fails → Probe not receiving `chat_events`
4. If some step missing → Fix that specific step

### Immediate Action

Add this debug logging to `agent.py` before next CI run:

```python
# Line 2193 - Before _accept_ingress
logger.info(f"DEBUG lk.chat raw data: sender={sender} data={data[:100]}")

# Line 2201 - After _accept_ingress check
logger.info(f"DEBUG lk.chat accepted: proceeding to _handle_text_chat_input")

# Line 1303 - Start of _handle_text_chat_input
logger.info(f"DEBUG _handle_text_chat_input: text={text[:50]} arch_phase={arch_phase}")

# Line 1407 - After response generation
logger.info(f"DEBUG response ready: publishing to chat_events")
```

These 4 log lines will pinpoint exactly where the message flow breaks.
