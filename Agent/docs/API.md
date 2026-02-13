# Maya-One Agent - API Documentation

## Tool Endpoints

The agent exposes the following tools via the LLM interface:

### Storage Tools

#### `set_alarm`
Set an alarm for a specific time.

**Parameters:**
- `time` (string, required): Alarm time in ISO format or natural language
- `label` (string, optional): Alarm label/description

**Returns:** Confirmation message

**Example:**
```json
{
  "tool": "set_alarm",
  "params": {
    "time": "2024-02-12T08:00:00Z",
    "label": "Morning meeting"
  }
}
```

#### `list_alarms`
List all active alarms for the user.

**Parameters:** None

**Returns:** List of active alarms

#### `set_reminder`
Create a reminder.

**Parameters:**
- `text` (string, required): Reminder text
- `time` (string, required): Reminder time

**Returns:** Confirmation message

#### `create_note`
Create a note.

**Parameters:**
- `title` (string, required): Note title
- `content` (string, required): Note content

**Returns:** Confirmation message

### System Tools

#### `get_current_time`
Get the current time.

**Parameters:** None

**Returns:** Current time string

#### `get_current_date`
Get the current date.

**Parameters:** None

**Returns:** Current date string

## Metrics API

Access metrics via the `MetricsCollector` class:

```python
from core.observability import metrics

# Get summary
summary = metrics.get_summary()

# Get specific stats
llm_stats = metrics.get_stats("llm_call_duration_seconds")
```

## Cache API

### LLM Cache

```python
from core.cache import llm_cache

# Check cache
response = llm_cache.get(messages, model)

# Set cache
llm_cache.set(messages, model, response)

# Get stats
stats = llm_cache.get_stats()
```

### Tool Cache

```python
from core.cache import tool_cache

# Check cache
result = tool_cache.get("get_weather", {"city": "London"})

# Set cache
tool_cache.set("get_weather", {"city": "London"}, result)
```

## Security

All user inputs are automatically sanitized via `InputSanitizer`:

- XSS prevention
- SQL injection prevention
- Input length limits
- Pattern validation

## Error Handling

All Supabase operations include automatic retry with exponential backoff (3 retries, base delay 0.5s).
