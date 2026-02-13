# Maya-One Agent - Troubleshooting Guide

## Common Issues

### 1. Supabase Connection Fails

**Symptoms:**
- "Supabase credentials not found" warning
- Persistence features not working

**Solutions:**
- Verify `.env` file contains `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`
- Check Supabase project is active (not paused)
- Verify service key has correct permissions
- Test connection: `python scripts/health_check.py`

### 2. LLM Rate Limits

**Symptoms:**
- "429 Too Many Requests" errors
- Agent stops responding

**Solutions:**
- Rate limiter is automatically enabled
- Adjust limits in `utils/rate_limiter.py`:
  ```python
  RateLimiter(max_calls=4, period=60)  # 4 calls per minute
  ```
- Consider upgrading API plan
- Enable LLM caching to reduce calls

### 3. Memory/Context Issues

**Symptoms:**
- Agent forgets previous conversations
- No personalization

**Solutions:**
- Verify `conversation_history` table exists in Supabase
- Check `MEM0_API_KEY` is set (optional but recommended)
- Ensure user_id is being correctly extracted
- Review logs for memory injection errors

### 4. Tool Execution Failures

**Symptoms:**
- Tools return errors
- "Tool not found" messages

**Solutions:**
- Check tool is registered in `tools/__init__.py`
- Verify tool signature matches expected format
- Review `logs/audit.log` for execution traces
- Test tool directly:
  ```python
  from tools.storage import set_alarm
  result = await set_alarm(context, time="10:00", label="Test")
  ```

### 5. Docker Container Won't Start

**Symptoms:**
- Container exits immediately
- Health check fails

**Solutions:**
- Check logs: `docker logs maya-agent`
- Verify all environment variables are passed
- Ensure port 8080 is available
- Run health check manually:
  ```bash
  docker exec maya-agent python scripts/health_check.py
  ```

### 6. High Latency

**Symptoms:**
- Slow responses
- Audio delays

**Solutions:**
- Enable caching (already enabled by default)
- Check Supabase region matches your deployment
- Review metrics:
  ```python
  from core.observability import metrics
  print(metrics.get_stats("llm_call_duration_seconds"))
  ```
- Consider using faster LLM provider
- Optimize database queries

### 7. Governance/Permission Errors

**Symptoms:**
- "Access denied" for tools
- Guest users can't perform actions

**Solutions:**
- Review user role assignment in `agent.py`
- Check `core/governance/policy.py` for tool risk levels
- Verify `ExecutionGate` is allowing expected operations
- Review audit logs: `logs/audit.log`

## Debug Mode

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Getting Help

1. Check logs in `logs/` directory
2. Review audit trail in `logs/audit.log`
3. Run health check: `python scripts/health_check.py`
4. Check metrics: `metrics.get_summary()`
5. Verify database connectivity via Supabase dashboard

## Performance Tuning

### Cache Hit Rate
Target: >60% for LLM cache

```python
from core.cache import llm_cache
stats = llm_cache.get_stats()
print(f"Hit rate: {stats['hit_rate']:.1%}")
```

### Database Query Time
Target: <100ms for most queries

Check Supabase dashboard for slow queries and add indexes as needed.

### LLM Response Time
Target: <2s for most queries

- Use faster models (e.g., Groq)
- Enable streaming responses
- Optimize prompts to be concise
