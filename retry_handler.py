#!/usr/bin/env python3
"""
Retry Handler - Comprehensive Error Recovery with Exponential Backoff
======================================================================
Provides retry decorators and utilities for all watchers and MCP servers
with graceful degradation and comprehensive JSON logging.

Features:
- Exponential backoff with jitter
- Configurable max attempts and delay
- Transient error detection (network, API timeouts)
- Graceful degradation (quarantine files when API down)
- Comprehensive JSON logging to Logs/YYYY-MM-DD.json

Usage:
    from retry_handler import retry_with_backoff, log_action
    
    @retry_with_backoff(max_attempts=3, delay=1.0)
    def api_call():
        # Your API call here
        pass
    
    # Log actions
    log_action(
        action_type="email_sent",
        actor="gmail_watcher",
        target="user@example.com",
        parameters={"subject": "Hello"},
        result="success"
    )

Cron Example:
    # No cron needed - runs with watchers
    # Automatically handles retries and logging
"""

import os
import sys
import io
import json
import logging
import time
import random
import functools
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable, Type, Tuple, List
from dataclasses import dataclass, asdict
from enum import Enum

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ============================================================================
# Configuration
# ============================================================================

LOGS_DIR = Path("./Logs")
QUARANTINE_DIR = Path("./Quarantine")

# Ensure directories exist
LOGS_DIR.mkdir(exist_ok=True)
QUARANTINE_DIR.mkdir(exist_ok=True)

# Retry Configuration
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 60.0  # seconds
DEFAULT_JITTER = 0.1  # 10% jitter

# Transient Error Patterns (strings that indicate retry-able errors)
TRANSIENT_ERROR_PATTERNS = [
    'timeout',
    'timed out',
    'connection',
    'network',
    'temporary',
    'retry',
    'rate limit',
    'too many requests',
    'service unavailable',
    'bad gateway',
    'gateway timeout',
    'connection reset',
    'connection refused',
    'connection aborted',
    'broken pipe',
    'ssl',
    'certificate',
    'dns',
    'socket',
    'urlopen',
    'httperror 5',  # 5xx server errors
    'httperror 429',  # Rate limiting
    'httperror 408',  # Request timeout
]

# Permanent Error Patterns (should NOT retry)
PERMANENT_ERROR_PATTERNS = [
    'authentication',
    'unauthorized',
    'forbidden',
    'permission',
    'access denied',
    'invalid credentials',
    'not found',
    '404',
    'bad request',
    '400',
    'invalid argument',
    'validation',
]


# ============================================================================
# Enums
# ============================================================================

class ActionResult(Enum):
    """Result status for action logging."""
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    QUARANTINED = "quarantined"
    SKIPPED = "skipped"


class ErrorType(Enum):
    """Classification of error types."""
    TRANSIENT = "transient"  # Can retry
    PERMANENT = "permanent"  # Should not retry
    UNKNOWN = "unknown"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class ActionLog:
    """Structured log entry for actions."""
    timestamp: str
    action_type: str
    actor: str
    target: str
    parameters: Dict[str, Any]
    result: str
    error: Optional[str] = None
    attempt: int = 1
    duration_ms: int = 0
    error_type: Optional[str] = None
    quarantined: bool = False


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    base_delay: float = DEFAULT_BASE_DELAY
    max_delay: float = DEFAULT_MAX_DELAY
    jitter: float = DEFAULT_JITTER
    exponential_base: float = 2.0
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    non_retryable_exceptions: Tuple[Type[Exception], ...] = ()


# ============================================================================
# JSON Logging
# ============================================================================

def get_today_log_file() -> Path:
    """Get path to today's JSON log file."""
    today = datetime.now().strftime("%Y-%m-%d")
    return LOGS_DIR / f"{today}.json"


def log_action(
    action_type: str,
    actor: str,
    target: str,
    parameters: Dict[str, Any],
    result: str,
    error: Optional[str] = None,
    attempt: int = 1,
    duration_ms: int = 0,
    error_type: Optional[str] = None,
    quarantined: bool = False
) -> Dict:
    """
    Log an action to the daily JSON log file.
    
    Args:
        action_type: Type of action (e.g., "email_sent", "api_call", "file_created")
        actor: Component performing the action (e.g., "gmail_watcher", "odoo_mcp")
        target: Target of the action (e.g., email address, API endpoint)
        parameters: Parameters passed to the action
        result: Result status ("success", "failure", "retry", "quarantined")
        error: Error message if failed
        attempt: Attempt number (for retries)
        duration_ms: Duration in milliseconds
        error_type: Classification of error ("transient", "permanent", "unknown")
        quarantined: Whether the item was quarantined
    
    Returns:
        The log entry dict that was written
    """
    log_entry = ActionLog(
        timestamp=datetime.now().isoformat(),
        action_type=action_type,
        actor=actor,
        target=target,
        parameters=parameters or {},
        result=result,
        error=error,
        attempt=attempt,
        duration_ms=duration_ms,
        error_type=error_type,
        quarantined=quarantined
    )
    
    log_data = asdict(log_entry)
    
    # Append to daily log file
    log_file = get_today_log_file()
    
    try:
        # Load existing entries or create new list
        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                try:
                    logs = json.load(f)
                except json.JSONDecodeError:
                    logs = []
        else:
            logs = []
        
        # Append new entry
        logs.append(log_data)
        
        # Write back
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
        
        # Also log to standard logging
        log_level = logging.INFO if result == "success" else logging.WARNING
        logging.log(log_level, f"Action: {action_type} | {actor} | {target} | {result}")
        
        return log_data
        
    except Exception as e:
        # If logging fails, don't fail the operation - just print error
        logging.error(f"Failed to write action log: {e}")
        return log_data


def get_action_logs(
    date: Optional[str] = None,
    actor: Optional[str] = None,
    action_type: Optional[str] = None,
    result: Optional[str] = None
) -> List[Dict]:
    """
    Retrieve action logs with optional filtering.
    
    Args:
        date: Date string (YYYY-MM-DD), defaults to today
        actor: Filter by actor name
        action_type: Filter by action type
        result: Filter by result status
    
    Returns:
        List of matching log entries
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    log_file = LOGS_DIR / f"{date}.json"
    
    if not log_file.exists():
        return []
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = json.load(f)
        
        # Apply filters
        filtered = logs
        
        if actor:
            filtered = [l for l in filtered if l.get('actor') == actor]
        if action_type:
            filtered = [l for l in filtered if l.get('action_type') == action_type]
        if result:
            filtered = [l for l in filtered if l.get('result') == result]
        
        return filtered
        
    except Exception as e:
        logging.error(f"Failed to read action logs: {e}")
        return []


# ============================================================================
# Error Classification
# ============================================================================

def classify_error(error: Exception) -> ErrorType:
    """
    Classify an error as transient (retry-able) or permanent.
    
    Args:
        error: The exception to classify
    
    Returns:
        ErrorType.TRANSIENT or ErrorType.PERMANENT
    """
    error_str = str(error).lower()
    error_name = type(error).__name__.lower()
    combined = f"{error_name} {error_str}"
    
    # Check for permanent error patterns first (higher priority)
    for pattern in PERMANENT_ERROR_PATTERNS:
        if pattern in combined:
            return ErrorType.PERMANENT
    
    # Check for transient error patterns
    for pattern in TRANSIENT_ERROR_PATTERNS:
        if pattern in combined:
            return ErrorType.TRANSIENT
    
    # Default: treat unknown errors as transient (safer for recovery)
    return ErrorType.TRANSIENT


def is_transient_error(error: Exception) -> bool:
    """Check if error is transient (should retry)."""
    return classify_error(error) == ErrorType.TRANSIENT


def is_permanent_error(error: Exception) -> bool:
    """Check if error is permanent (should not retry)."""
    return classify_error(error) == ErrorType.PERMANENT


# ============================================================================
# Retry Decorator
# ============================================================================

def retry_with_backoff(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
    exponential_base: float = 2.0,
    logger: Optional[logging.Logger] = None,
    log_actor: Optional[str] = None,
    on_retry: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
    quarantine_on_failure: bool = True
):
    """
    Decorator for retry with exponential backoff and jitter.
    
    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay cap in seconds
        jitter: Jitter factor (0.0-1.0) to add randomness
        exponential_base: Base for exponential backoff (2.0 = doubles each time)
        logger: Logger instance for messages
        log_actor: Actor name for action logging
        on_retry: Callback function called on each retry
        on_failure: Callback function called on final failure
        quarantine_on_failure: Whether to quarantine on final failure
    
    Returns:
        Decorated function with retry behavior
    
    Example:
        @retry_with_backoff(max_attempts=3, base_delay=1.0)
        def fetch_email():
            # Your code here
            pass
    """
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            nonlocal logger
            
            # Use provided logger or get function's module logger
            if logger is None:
                logger = logging.getLogger(func.__module__)
            
            # Determine actor name for logging
            actor = log_actor or func.__module__ or "unknown"
            
            # Track attempts and timing
            attempt = 0
            last_error = None
            start_time = time.time()
            
            while attempt < max_attempts:
                attempt += 1
                
                try:
                    # Execute the function
                    result = func(*args, **kwargs)
                    
                    # Success - log and return
                    duration_ms = int((time.time() - start_time) * 1000)
                    
                    log_action(
                        action_type=func.__name__,
                        actor=actor,
                        target=str(args[0]) if args else "unknown",
                        parameters=kwargs,
                        result=ActionResult.SUCCESS.value,
                        attempt=attempt,
                        duration_ms=duration_ms
                    )
                    
                    logger.info(f"{func.__name__} succeeded on attempt {attempt}/{max_attempts}")
                    return result
                    
                except Exception as e:
                    last_error = e
                    error_type = classify_error(e)
                    duration_ms = int((time.time() - start_time) * 1000)
                    
                    # Check if error is retry-able
                    if error_type == ErrorType.PERMANENT:
                        # Don't retry permanent errors
                        logger.error(f"{func.__name__} failed with permanent error: {e}")
                        
                        log_action(
                            action_type=func.__name__,
                            actor=actor,
                            target=str(args[0]) if args else "unknown",
                            parameters=kwargs,
                            result=ActionResult.FAILURE.value,
                            error=str(e),
                            attempt=attempt,
                            duration_ms=duration_ms,
                            error_type=error_type.value
                        )
                        
                        if on_failure:
                            on_failure(e, attempt)
                        
                        raise
                    
                    # Log retry attempt
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}"
                    )
                    
                    log_action(
                        action_type=func.__name__,
                        actor=actor,
                        target=str(args[0]) if args else "unknown",
                        parameters=kwargs,
                        result=ActionResult.RETRY.value,
                        error=str(e),
                        attempt=attempt,
                        duration_ms=duration_ms,
                        error_type=error_type.value
                    )
                    
                    # Call retry callback if provided
                    if on_retry:
                        on_retry(e, attempt, max_attempts)
                    
                    # If this was the last attempt, handle failure
                    if attempt >= max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        
                        log_action(
                            action_type=func.__name__,
                            actor=actor,
                            target=str(args[0]) if args else "unknown",
                            parameters=kwargs,
                            result=ActionResult.FAILURE.value,
                            error=str(e),
                            attempt=attempt,
                            duration_ms=duration_ms,
                            error_type=error_type.value,
                            quarantined=quarantine_on_failure
                        )
                        
                        if on_failure:
                            on_failure(e, attempt)
                        
                        raise
                    
                    # Calculate delay with exponential backoff and jitter
                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay
                    )
                    
                    # Add jitter
                    jitter_range = delay * jitter
                    delay += random.uniform(-jitter_range, jitter_range)
                    delay = max(0, delay)  # Ensure non-negative
                    
                    logger.info(f"Retrying {func.__name__} in {delay:.2f} seconds...")
                    time.sleep(delay)
            
            # Should not reach here, but just in case
            raise last_error
        
        return wrapper
    return decorator


# ============================================================================
# Async Retry Decorator
# ============================================================================

def async_retry_with_backoff(
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
    exponential_base: float = 2.0,
    logger: Optional[logging.Logger] = None,
    log_actor: Optional[str] = None,
    on_retry: Optional[Callable] = None,
    on_failure: Optional[Callable] = None,
    quarantine_on_failure: bool = True
):
    """
    Async version of retry_with_backoff decorator.
    
    For use with async functions (asyncio).
    
    Example:
        @async_retry_with_backoff(max_attempts=3)
        async def fetch_data():
            # Your async code here
            pass
    """
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            import asyncio
            
            nonlocal logger
            
            if logger is None:
                logger = logging.getLogger(func.__module__)
            
            actor = log_actor or func.__module__ or "unknown"
            
            attempt = 0
            last_error = None
            start_time = time.time()
            
            while attempt < max_attempts:
                attempt += 1
                
                try:
                    result = await func(*args, **kwargs)
                    
                    duration_ms = int((time.time() - start_time) * 1000)
                    
                    log_action(
                        action_type=func.__name__,
                        actor=actor,
                        target=str(args[0]) if args else "unknown",
                        parameters=kwargs,
                        result=ActionResult.SUCCESS.value,
                        attempt=attempt,
                        duration_ms=duration_ms
                    )
                    
                    logger.info(f"{func.__name__} succeeded on attempt {attempt}/{max_attempts}")
                    return result
                    
                except Exception as e:
                    last_error = e
                    error_type = classify_error(e)
                    duration_ms = int((time.time() - start_time) * 1000)
                    
                    if error_type == ErrorType.PERMANENT:
                        logger.error(f"{func.__name__} failed with permanent error: {e}")
                        
                        log_action(
                            action_type=func.__name__,
                            actor=actor,
                            target=str(args[0]) if args else "unknown",
                            parameters=kwargs,
                            result=ActionResult.FAILURE.value,
                            error=str(e),
                            attempt=attempt,
                            duration_ms=duration_ms,
                            error_type=error_type.value
                        )
                        
                        if on_failure:
                            on_failure(e, attempt)
                        
                        raise
                    
                    logger.warning(
                        f"{func.__name__} failed (attempt {attempt}/{max_attempts}): {e}"
                    )
                    
                    log_action(
                        action_type=func.__name__,
                        actor=actor,
                        target=str(args[0]) if args else "unknown",
                        parameters=kwargs,
                        result=ActionResult.RETRY.value,
                        error=str(e),
                        attempt=attempt,
                        duration_ms=duration_ms,
                        error_type=error_type.value
                    )
                    
                    if on_retry:
                        on_retry(e, attempt, max_attempts)
                    
                    if attempt >= max_attempts:
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        
                        log_action(
                            action_type=func.__name__,
                            actor=actor,
                            target=str(args[0]) if args else "unknown",
                            parameters=kwargs,
                            result=ActionResult.FAILURE.value,
                            error=str(e),
                            attempt=attempt,
                            duration_ms=duration_ms,
                            error_type=error_type.value,
                            quarantined=quarantine_on_failure
                        )
                        
                        if on_failure:
                            on_failure(e, attempt)
                        
                        raise
                    
                    delay = min(
                        base_delay * (exponential_base ** (attempt - 1)),
                        max_delay
                    )
                    
                    jitter_range = delay * jitter
                    delay += random.uniform(-jitter_range, jitter_range)
                    delay = max(0, delay)
                    
                    logger.info(f"Retrying {func.__name__} in {delay:.2f} seconds...")
                    await asyncio.sleep(delay)
            
            raise last_error
        
        return wrapper
    return decorator


# ============================================================================
# Quarantine Management
# ============================================================================

def quarantine_item(
    item_type: str,
    item_content: str,
    source: str,
    reason: str,
    error: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> str:
    """
    Move an item to quarantine when processing fails.
    
    Args:
        item_type: Type of item (e.g., "email", "task", "invoice")
        item_content: Content of the item
        source: Source location/identifier
        reason: Reason for quarantine
        error: Error message that caused quarantine
        metadata: Additional metadata to store
    
    Returns:
        Path to quarantined file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"QUARANTINE_{item_type}_{timestamp}.md"
    filepath = QUARANTINE_DIR / filename
    
    # Build quarantine file content
    content = f"""---
type: quarantined
item_type: {item_type}
source: {source}
quarantined_at: {datetime.now().isoformat()}
reason: {reason}
error: {error or 'N/A'}
---

# Quarantined Item

**Type**: {item_type}
**Source**: {source}
**Quarantined**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Reason**: {reason}

## Error Details
```
{error or 'No error details available'}
```

## Original Content
{item_content}

## Metadata
```json
{json.dumps(metadata or {}, indent=2)}
```

---
**Action Required**: Review this item manually and either:
1. Fix the issue and move to appropriate processing directory
2. Delete if no longer relevant
3. Move back to source if quarantined in error
"""
    
    # Write quarantine file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # Log the quarantine action
    log_action(
        action_type="quarantine",
        actor="retry_handler",
        target=str(filepath),
        parameters={
            "item_type": item_type,
            "source": source,
            "reason": reason
        },
        result=ActionResult.QUARANTINED.value,
        error=error
    )
    
    logger.warning(f"Item quarantined: {filepath}")
    
    return str(filepath)


def get_quarantined_items() -> List[Dict]:
    """
    Get all quarantined items with their details.
    
    Returns:
        List of dicts with quarantine file info
    """
    items = []
    
    if not QUARANTINE_DIR.exists():
        return items
    
    for filepath in QUARANTINE_DIR.glob("QUARANTINE_*.md"):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse frontmatter
            import re
            frontmatter_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            
            metadata = {}
            if frontmatter_match:
                frontmatter = frontmatter_match.group(1)
                for line in frontmatter.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        metadata[key.strip()] = value.strip()
            
            items.append({
                'filepath': str(filepath),
                'filename': filepath.name,
                'metadata': metadata,
                'content': content
            })
            
        except Exception as e:
            logger.error(f"Error reading quarantine file {filepath}: {e}")
    
    return items


def release_from_quarantine(filepath: str, destination: str) -> bool:
    """
    Release an item from quarantine to a destination directory.
    
    Args:
        filepath: Path to quarantine file
        destination: Destination directory path
    
    Returns:
        True if successful
    """
    import shutil
    
    try:
        src = Path(filepath)
        dst = Path(destination)
        dst.mkdir(exist_ok=True)
        
        # Move file
        shutil.move(str(src), str(dst / src.name))
        
        log_action(
            action_type="release_quarantine",
            actor="retry_handler",
            target=str(filepath),
            parameters={"destination": str(destination)},
            result=ActionResult.SUCCESS.value
        )
        
        logger.info(f"Released from quarantine: {filepath} -> {destination}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to release from quarantine: {e}")
        return False


# ============================================================================
# Health Check Utilities
# ============================================================================

def get_system_health() -> Dict:
    """
    Get system health status including retry statistics.
    
    Returns:
        Dict with health metrics
    """
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = get_today_log_file()
    
    # Load today's logs
    logs = []
    if log_file.exists():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except:
            pass
    
    # Calculate statistics
    total_actions = len(logs)
    successful = len([l for l in logs if l.get('result') == 'success'])
    failed = len([l for l in logs if l.get('result') == 'failure'])
    retried = len([l for l in logs if l.get('result') == 'retry'])
    quarantined = len([l for l in logs if l.get('quarantined') == True])
    
    # Group by actor
    by_actor = {}
    for log in logs:
        actor = log.get('actor', 'unknown')
        if actor not in by_actor:
            by_actor[actor] = {'total': 0, 'success': 0, 'failure': 0}
        by_actor[actor]['total'] += 1
        if log.get('result') == 'success':
            by_actor[actor]['success'] += 1
        elif log.get('result') == 'failure':
            by_actor[actor]['failure'] += 1
    
    # Get quarantine count
    quarantine_count = len(list(QUARANTINE_DIR.glob("QUARANTINE_*.md")))
    
    return {
        'timestamp': datetime.now().isoformat(),
        'date': today,
        'summary': {
            'total_actions': total_actions,
            'successful': successful,
            'failed': failed,
            'retried': retried,
            'quarantined': quarantined,
            'success_rate': (successful / total_actions * 100) if total_actions > 0 else 0
        },
        'by_actor': by_actor,
        'quarantine_count': quarantine_count
    }


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Example: Sync function with retry
    @retry_with_backoff(max_attempts=3, base_delay=1.0, log_actor="example")
    def example_api_call(url: str):
        import urllib.request
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.read()
    
    # Example: Async function with retry
    import asyncio
    
    @async_retry_with_backoff(max_attempts=3, base_delay=1.0, log_actor="async_example")
    async def example_async_call(url: str):
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as response:
                return await response.text()
    
    # Example: Quarantine usage
    def process_email(email_content: str):
        try:
            # Processing that might fail
            raise Exception("API timeout")
        except Exception as e:
            quarantine_item(
                item_type="email",
                item_content=email_content,
                source="gmail_watcher",
                reason="Processing failed after retries",
                error=str(e)
            )
    
    # Run examples
    print("Retry Handler Demo")
    print("=" * 60)
    
    # Test with a URL that will fail (to demonstrate retry)
    try:
        example_api_call("http://invalid-url-test-12345.com")
    except Exception as e:
        print(f"Final failure (expected): {e}")
    
    # Show health status
    print("\nSystem Health:")
    print(json.dumps(get_system_health(), indent=2))
    
    print("\n" + "=" * 60)
    print("Check Logs/" + datetime.now().strftime("%Y-%m-%d") + ".json for action logs")
