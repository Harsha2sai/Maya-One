# Maya-One

Maya-One is a voice-first AI assistant stack with:
- `Agent/` backend (LiveKit + orchestration + tools + memory)
- Flutter client integration (separate app tree)
- CI certification gates for regression and live voice probes

## Quick Start (Agent)

```bash
cd Agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create `Agent/.env` with required runtime variables:

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=...
LIVEKIT_URL=wss://...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
LIVEKIT_AGENT_NAME=maya-one
```

Run local dev worker + token server:

```bash
cd Agent
source venv/bin/activate
python agent.py dev
```

## Test Commands

Full regression:

```bash
cd Agent
source venv/bin/activate
python -m pytest tests/ -q
```

Voice certification (Phase 27 suite):

```bash
cd Agent
source venv/bin/activate
bash scripts/run_phase27_voice_certification.sh
```

Expected passing result:
- `CERT_RESULT PASS`
- probes: `factual_math`, `identity_creator`, `time_fastpath`

## CI Certification Gate

Workflow: `.github/workflows/phase27-cert.yml`

CI requires repository secrets:
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `GROQ_API_KEY` (or configure `OPENAI_API_KEY` if provider switched)

The workflow runs in parallel:
- full regression (`pytest tests/`)
- live voice certification (`run_phase27_voice_certification.sh`)

## Production Readiness Checklist

- Full local regression green
- Voice certification green
- CI regression + voice jobs green on `main`
- Release tag pushed (`v0.28.0` or newer)

For deployment details, see `docs/PRODUCTION_DEPLOYMENT.md`.
