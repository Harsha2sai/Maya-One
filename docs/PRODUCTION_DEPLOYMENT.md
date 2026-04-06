# Production Deployment Guide

## 1. Required Secrets and Runtime Env

### GitHub Actions secrets
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `GROQ_API_KEY` (or `OPENAI_API_KEY` if using OpenAI)

### Agent runtime env (`Agent/.env`)
- `LLM_PROVIDER` (`groq` by default)
- `GROQ_API_KEY` (or provider-specific key)
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `LIVEKIT_AGENT_NAME=maya-one`

## 2. Local Production Gate

```bash
cd Agent
source venv/bin/activate
python -m pytest tests/ -q
bash scripts/run_phase27_voice_certification.sh
```

Gate is considered green only when:
- tests complete with no failures
- `CERT_RESULT PASS` with all three probes passing

## 3. CI Production Gate

Trigger workflow:

```bash
gh workflow run phase27-cert.yml --ref main
```

Validate latest run:

```bash
gh run list --workflow phase27-cert.yml --limit 1
gh run view <run-id> --log
```

Both jobs must pass:
- `Full Regression Suite`
- `Voice Certification Probes`

## 4. Release Process

```bash
git tag v0.28.0
git push origin main --tags
```

Optional post-tag certification:

```bash
gh workflow run phase27-cert.yml --ref v0.28.0
```

## 5. Troubleshooting

- `CERT_RESULT SETUP_FAILURE token_server_unreachable`: verify backend process and `:5050` token server startup.
- `agent_not_joined`: verify LiveKit credentials and `LIVEKIT_AGENT_NAME`.
- intermittent probe failures: rerun certification and inspect `/tmp/maya_phase27_cert.json` and `/tmp/maya_phase27_backend.log`.
