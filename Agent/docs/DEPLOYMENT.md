# Maya-One Agent - Deployment Guide

## Prerequisites

- Docker (for containerized deployment)
- Supabase account with project created
- LiveKit Cloud account or self-hosted LiveKit server
- API keys for LLM providers (Groq, OpenAI, etc.)

## Environment Variables

Create a `.env` file with the following:

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-key

# LiveKit
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# LLM Providers
GROQ_API_KEY=your-groq-key
OPENAI_API_KEY=your-openai-key
GOOGLE_API_KEY=your-google-key

# Optional
MEM0_API_KEY=your-mem0-key
```

## Database Setup

1. Run the schema files in your Supabase SQL Editor:
   ```bash
   # Base schema (Phase 1)
   cat final_schema.sql | supabase db execute

   # Phase 2 extensions
   cat phase2_schema.sql | supabase db execute
   ```

2. Verify tables are created:
   - `user_profiles`
   - `user_sessions`
   - `user_alarms`
   - `user_reminders`
   - `user_notes`
   - `user_calendar_events`
   - `conversation_history`

## Docker Deployment

### Build the image:
```bash
docker build -t maya-one-agent .
```

### Run the container:
```bash
docker run -d \
  --name maya-agent \
  --env-file .env \
  -p 8080:8080 \
  maya-one-agent
```

### Health check:
```bash
docker exec maya-agent python scripts/health_check.py
```

## Local Development

### Install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run the agent:
```bash
# Console mode (text-based)
python -m livekit.agents.cli console

# Production mode
python -m livekit.agents.cli start
```

## Monitoring

### View metrics:
```python
from core.observability import metrics
print(metrics.get_summary())
```

### View logs:
Logs are written to `logs/audit.log` in JSON format.

### Cache statistics:
```python
from core.cache import llm_cache, tool_cache
print(llm_cache.get_stats())
print(tool_cache.get_stats())
```

## Production Checklist

- [ ] All environment variables set
- [ ] Database schema applied
- [ ] Health check passing
- [ ] Logs directory writable
- [ ] API keys valid and tested
- [ ] Rate limits configured
- [ ] Monitoring enabled
- [ ] Backup strategy in place

## Scaling

For high-traffic deployments:

1. **Horizontal Scaling**: Run multiple agent instances behind a load balancer
2. **Database**: Use Supabase connection pooling
3. **Caching**: Consider Redis for distributed caching
4. **Monitoring**: Integrate with Prometheus/Grafana

## Troubleshooting

See `docs/TROUBLESHOOTING.md` for common issues and solutions.
