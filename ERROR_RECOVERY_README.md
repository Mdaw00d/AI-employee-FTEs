# Error Recovery System - Implementation Guide

## Overview

Comprehensive error recovery system with exponential backoff, graceful degradation, and JSON logging for all watchers and MCP servers.

## Components

### 1. retry_handler.py

Core retry handler module with:
- `@retry_with_backoff` - Sync function decorator
- `@async_retry_with_backoff` - Async function decorator
- `log_action()` - JSON logging
- `quarantine_item()` - Graceful degradation
- `get_system_health()` - Health monitoring

### 2. Updated Watchers

- `gmail_watcher_updated.py` - Gmail watcher with retry
- `odoo_mcp_updated.py` - Odoo MCP with retry

### 3. Quarantine Directory

- `Quarantine/` - Failed items stored for manual review

### 4. JSON Logs

- `Logs/YYYY-MM-DD.json` - Daily action logs

---

## Usage

### Basic Retry Decorator

```python
from retry_handler import retry_with_backoff, log_action

@retry_with_backoff(
    max_attempts=3,
    base_delay=1.0,
    max_delay=60.0,
    log_actor="my_service",
    quarantine_on_failure=True
)
def api_call(url: str):
    import urllib.request
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read()
```

### Async Retry Decorator

```python
from retry_handler import async_retry_with_backoff

@async_retry_with_backoff(
    max_attempts=3,
    base_delay=1.0,
    log_actor="async_service"
)
async def fetch_data(url: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
```

### Manual Logging

```python
from retry_handler import log_action

# Log success
log_action(
    action_type="email_sent",
    actor="gmail_watcher",
    target="user@example.com",
    parameters={"subject": "Hello"},
    result="success",
    duration_ms=150
)

# Log failure
log_action(
    action_type="api_call",
    actor="odoo_mcp",
    target="localhost:8069",
    parameters={},
    result="failure",
    error="Connection timeout",
    error_type="transient"
)
```

### Quarantine Failed Items

```python
from retry_handler import quarantine_item

filepath = quarantine_item(
    item_type="email",
    item_content=email_body,
    source="gmail_watcher",
    reason="Processing failed after 3 retries",
    error="SMTP timeout",
    metadata={"message_id": "12345"}
)
```

---

## Configuration

### Retry Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_attempts` | 3 | Maximum retry attempts |
| `base_delay` | 1.0 | Initial delay (seconds) |
| `max_delay` | 60.0 | Maximum delay cap |
| `jitter` | 0.1 | Randomness factor (0.0-1.0) |
| `exponential_base` | 2.0 | Backoff multiplier |

### Error Classification

**Transient Errors (will retry):**
- Network timeouts
- Connection errors
- Rate limiting (429)
- Server errors (5xx)
- SSL/TLS issues

**Permanent Errors (won't retry):**
- Authentication failures
- Permission denied
- Not found (404)
- Bad request (400)
- Invalid arguments

---

## Logging Format

### JSON Log Entry

```json
{
  "timestamp": "2026-03-07T14:30:00.123456",
  "action_type": "create_invoice",
  "actor": "odoo_mcp",
  "target": "localhost:8069",
  "parameters": {
    "partner_id": 42,
    "amount": 1000.00
  },
  "result": "success",
  "attempt": 1,
  "duration_ms": 234,
  "error_type": null,
  "quarantined": false
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 timestamp |
| `action_type` | string | Function/action name |
| `actor` | string | Component name |
| `target` | string | Target resource |
| `parameters` | object | Input parameters |
| `result` | string | success/failure/retry/quarantined |
| `error` | string | Error message (if failed) |
| `attempt` | integer | Attempt number |
| `duration_ms` | integer | Duration in milliseconds |
| `error_type` | string | transient/permanent/unknown |
| `quarantined` | boolean | Was item quarantined |

---

## Graceful Degradation

### Quarantine Flow

```
1. Function fails after max retries
2. Item quarantined to Quarantine/QUARANTINE_<type>_<timestamp>.md
3. Alert logged to JSON log
4. System continues operating
5. Manual review required for quarantined items
```

### Quarantine File Format

```markdown
---
type: quarantined
item_type: email
source: gmail_watcher
quarantined_at: 2026-03-07T14:30:00
reason: Processing failed after retries
error: SMTP timeout
---

# Quarantined Item

**Type**: email
**Source**: gmail_watcher
**Quarantined**: 2026-03-07 14:30:00
**Reason**: Processing failed after retries

## Error Details
```
SMTP timeout
```

## Original Content
[original content here]
```

---

## Health Monitoring

### Get System Health

```python
from retry_handler import get_system_health

health = get_system_health()
print(health)
```

### Health Output

```json
{
  "timestamp": "2026-03-07T14:30:00",
  "date": "2026-03-07",
  "summary": {
    "total_actions": 150,
    "successful": 142,
    "failed": 5,
    "retried": 8,
    "quarantined": 3,
    "success_rate": 94.67
  },
  "by_actor": {
    "gmail_watcher": {"total": 50, "success": 48, "failure": 2},
    "odoo_mcp": {"total": 100, "success": 94, "failure": 3}
  },
  "quarantine_count": 3
}
```

---

## Example: Updating a Watcher

### Before (no retry)

```python
def fetch_email():
    service = build('gmail', 'v1', credentials=creds)
    messages = service.users().messages().list(userId='me').execute()
    return messages
```

### After (with retry)

```python
from retry_handler import retry_with_backoff

@retry_with_backoff(
    max_attempts=3,
    base_delay=1.0,
    log_actor="gmail_watcher"
)
def fetch_email():
    service = build('gmail', 'v1', credentials=creds)
    messages = service.users().messages().list(userId='me').execute()
    return messages
```

---

## Cron Schedule

No cron changes needed - retry handler runs with watchers.

```bash
# Existing watcher cron - now with automatic retry
0 */5 * * * python /path/to/gmail_watcher.py >> Logs/gmail_watcher.log 2>&1
```

---

## Migration Checklist

- [ ] Import `retry_handler` module
- [ ] Add `@retry_with_backoff` to API calls
- [ ] Add `log_action()` calls for key operations
- [ ] Handle quarantine for critical failures
- [ ] Update logging to include JSON format
- [ ] Test retry behavior with simulated failures
- [ ] Monitor `Logs/YYYY-MM-DD.json` for action tracking

---

## Files Created

| File | Purpose |
|------|---------|
| `retry_handler.py` | Core retry handler module |
| `gmail_watcher_updated.py` | Gmail watcher with retry |
| `odoo_mcp_updated.py` | Odoo MCP with retry |
| `ERROR_RECOVERY_README.md` | This documentation |

---

## Quick Reference

### Decorator Template

```python
@retry_with_backoff(
    max_attempts=3,
    base_delay=1.0,
    max_delay=60.0,
    jitter=0.1,
    log_actor="service_name",
    quarantine_on_failure=True
)
def my_function():
    pass
```

### Log Action Template

```python
log_action(
    action_type="operation_name",
    actor="component_name",
    target="resource",
    parameters={"key": "value"},
    result="success",  # or "failure"
    error="error message",  # if failed
    duration_ms=100
)
```

### Quarantine Template

```python
quarantine_item(
    item_type="type",
    item_content="content",
    source="source_component",
    reason="failure reason",
    error="error message",
    metadata={"key": "value"}
)
```
