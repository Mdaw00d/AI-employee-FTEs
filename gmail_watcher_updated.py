#!/usr/bin/env python3
"""
Gmail Watcher - Monitors Gmail for important unread emails requiring action
================================================================================
Updated with retry_handler for error recovery and graceful degradation.

Features:
- Exponential backoff retry on transient errors
- Quarantine failed emails for manual review
- Comprehensive JSON logging to Logs/YYYY-MM-DD.json
- OAuth2 authentication with token refresh

First Run Setup:
1. Ensure credentials.json (Gmail OAuth) is in the project root
2. Run: python gmail_watcher.py
3. Browser will open - complete OAuth consent
4. token.json will be created automatically

Persistent Operation:
    pm2 start gmail_watcher.py --interpreter python --name gmail-watcher

Dependencies:
    pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2
"""

import os
import sys
import io
import time
import logging
import pickle
import base64
import random
from datetime import datetime
from pathlib import Path
from email import message_from_bytes

# Google API imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Import retry handler
from retry_handler import (
    retry_with_backoff,
    async_retry_with_backoff,
    log_action,
    quarantine_item,
    classify_error,
    is_transient_error,
    get_system_health
)

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ============================================================================
# Configuration
# ============================================================================

# Gmail API SCOPES
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Polling interval in seconds
POLL_INTERVAL = 120

# Retry Configuration
MAX_RETRIES = 3
BASE_BACKOFF = 2.0  # seconds
MAX_BACKOFF = 60.0  # seconds

# Gmail query for important emails
GMAIL_QUERY = 'is:unread is:important'

# File paths
CREDENTIALS_FILE = './credentials.json'
TOKEN_FILE = './token.json'
PROCESSED_IDS_FILE = './processed_ids.pkl'
NEEDS_ACTION_DIR = Path('./Needs_Action')
LOGS_DIR = Path('./Logs')
QUARANTINE_DIR = Path('./Quarantine')

# Ensure directories exist
for directory in [NEEDS_ACTION_DIR, LOGS_DIR, QUARANTINE_DIR]:
    directory.mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / 'gmail_watcher.log', encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)

logger = logging.getLogger(__name__)

# Force UTF-8 for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ============================================================================
# Retry-Wrapped Gmail Operations
# ============================================================================

@retry_with_backoff(
    max_attempts=MAX_RETRIES,
    base_delay=BASE_BACKOFF,
    max_delay=MAX_BACKOFF,
    log_actor="gmail_watcher",
    quarantine_on_failure=True
)
def get_gmail_service():
    """
    Get authenticated Gmail service with retry.
    
    Returns:
        Gmail API service object or None
    """
    creds = None
    
    # Load existing token
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            logger.info(f"Loaded token from {TOKEN_FILE}")
        except Exception as e:
            logger.warning(f"Failed to load token: {e}")
            creds = None
    
    # Refresh or obtain new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Refreshing expired token...")
                creds.refresh(Request())
                logger.info("Token refreshed")
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}")
                creds = None
        
        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                logger.error(f"Credentials not found: {CREDENTIALS_FILE}")
                log_action(
                    action_type="authentication",
                    actor="gmail_watcher",
                    target=CREDENTIALS_FILE,
                    parameters={},
                    result="failure",
                    error="Credentials file not found"
                )
                return None
            
            try:
                logger.info("Starting OAuth flow...")
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0, open_browser=False)
                
                with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                    f.write(creds.to_json())
                logger.info(f"Credentials saved to {TOKEN_FILE}")
                
            except Exception as e:
                logger.error(f"OAuth failed: {e}")
                log_action(
                    action_type="authentication",
                    actor="gmail_watcher",
                    target=CREDENTIALS_FILE,
                    parameters={},
                    result="failure",
                    error=str(e)
                )
                return None
    
    # Build service
    service = build('gmail', 'v1', credentials=creds)
    
    log_action(
        action_type="authentication",
        actor="gmail_watcher",
        target="gmail_api",
        parameters={},
        result="success"
    )
    
    return service


@retry_with_backoff(
    max_attempts=MAX_RETRIES,
    base_delay=BASE_BACKOFF,
    max_delay=MAX_BACKOFF,
    log_actor="gmail_watcher",
    quarantine_on_failure=False
)
def list_gmail_messages(service, query: str, max_results: int = 10):
    """
    List Gmail messages matching query with retry.
    
    Args:
        service: Gmail API service
        query: Gmail search query
        max_results: Maximum results to return
    
    Returns:
        List of message dicts
    """
    try:
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        logger.info(f"Found {len(messages)} messages matching: {query}")
        
        log_action(
            action_type="list_messages",
            actor="gmail_watcher",
            target="gmail_api",
            parameters={"query": query, "max_results": max_results},
            result="success"
        )
        
        return messages
        
    except HttpError as e:
        # HTTP errors from Gmail API
        logger.error(f"Gmail API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to list messages: {e}")
        raise


@retry_with_backoff(
    max_attempts=MAX_RETRIES,
    base_delay=BASE_BACKOFF,
    max_delay=MAX_BACKOFF,
    log_actor="gmail_watcher",
    quarantine_on_failure=False
)
def get_gmail_message(service, message_id: str):
    """
    Get full Gmail message with retry.
    
    Args:
        service: Gmail API service
        message_id: Gmail message ID
    
    Returns:
        Message data dict
    """
    try:
        message = service.users().messages().get(
            userId='me',
            id=message_id,
            format='raw'
        ).execute()
        
        log_action(
            action_type="get_message",
            actor="gmail_watcher",
            target=message_id,
            parameters={},
            result="success"
        )
        
        return message
        
    except HttpError as e:
        logger.error(f"Gmail API error getting message {message_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to get message {message_id}: {e}")
        raise


# ============================================================================
# Processed IDs Management
# ============================================================================

def load_processed_ids():
    """Load set of processed message IDs."""
    if os.path.exists(PROCESSED_IDS_FILE):
        try:
            with open(PROCESSED_IDS_FILE, 'rb') as f:
                processed_ids = pickle.load(f)
            logger.info(f"Loaded {len(processed_ids)} processed IDs")
            return processed_ids
        except Exception as e:
            logger.warning(f"Failed to load processed IDs: {e}")
            return set()
    return set()


def save_processed_ids(processed_ids: set):
    """Save processed message IDs."""
    try:
        with open(PROCESSED_IDS_FILE, 'wb') as f:
            pickle.dump(processed_ids, f)
        logger.info(f"Saved {len(processed_ids)} processed IDs")
        
        log_action(
            action_type="save_state",
            actor="gmail_watcher",
            target=PROCESSED_IDS_FILE,
            parameters={"count": len(processed_ids)},
            result="success"
        )
    except Exception as e:
        logger.error(f"Failed to save processed IDs: {e}")
        log_action(
            action_type="save_state",
            actor="gmail_watcher",
            target=PROCESSED_IDS_FILE,
            parameters={},
            result="failure",
            error=str(e)
        )


# ============================================================================
# Email Processing
# ============================================================================

def decode_mime_header(header_value):
    """Decode MIME-encoded header values."""
    if not header_value:
        return ""
    try:
        from email.header import decode_header
        decoded_parts = decode_header(header_value)
        result = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result += part.decode(encoding or 'utf-8', errors='replace')
            else:
                result += part
        return result
    except Exception:
        return header_value


def decode_base64_url_safe(data: str) -> bytes:
    """Decode URL-safe base64 data."""
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    data = data.replace('-', '+').replace('_', '/')
    return base64.b64decode(data)


def extract_email_data(raw_message: str) -> dict:
    """Extract email data from raw Gmail message."""
    try:
        message_bytes = decode_base64_url_safe(raw_message)
        msg = message_from_bytes(message_bytes)
        
        email_from = decode_mime_header(msg.get('From', ''))
        subject = decode_mime_header(msg.get('Subject', ''))
        date = decode_mime_header(msg.get('Date', ''))
        to = decode_mime_header(msg.get('To', ''))
        
        # Extract body
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == 'text/plain':
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        body = part.get_payload(decode=True).decode(charset, errors='replace')
                        break
                    except Exception:
                        continue
        
        if not body:
            body = msg.get_payload(decode=True).decode('utf-8', errors='replace') if msg.get_payload() else ""
        
        return {
            'from': email_from,
            'to': to,
            'subject': subject,
            'date': date,
            'body': body[:500]  # First 500 chars for snippet
        }
        
    except Exception as e:
        logger.error(f"Failed to extract email data: {e}")
        return {
            'from': 'Unknown',
            'subject': 'Error decoding email',
            'body': str(e)
        }


def create_task_file(email_data: dict, message_id: str) -> str:
    """
    Create a task file in Needs_Action/ for the email.
    
    Args:
        email_data: Extracted email data
        message_id: Gmail message ID
    
    Returns:
        Path to created file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"EMAIL_{timestamp}_{message_id[:8]}.md"
    filepath = NEEDS_ACTION_DIR / filename
    
    # Determine priority based on subject keywords
    subject_lower = email_data.get('subject', '').lower()
    priority = 'normal'
    for keyword in ['urgent', 'asap', 'emergency', 'critical']:
        if keyword in subject_lower:
            priority = 'high'
            break
    
    content = f"""---
type: email
from: {email_data.get('from', 'Unknown')}
subject: {email_data.get('subject', 'No Subject')}
received: {email_data.get('date', 'Unknown')}
priority: {priority}
message_id: {message_id}
---

# Email Task

**From**: {email_data.get('from', 'Unknown')}
**Subject**: {email_data.get('subject', 'No Subject')}
**Received**: {email_data.get('date', 'Unknown')}
**Priority**: {priority}

## Message Body
```
{email_data.get('body', 'No content')}
```

---
**Processing Instructions**:
1. Review email content
2. Determine required action
3. Create approval if action needed
4. Move to Done/ when complete
"""
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"Created task file: {filepath}")
        
        log_action(
            action_type="create_task",
            actor="gmail_watcher",
            target=str(filepath),
            parameters={
                "from": email_data.get('from'),
                "subject": email_data.get('subject'),
                "priority": priority
            },
            result="success"
        )
        
        return str(filepath)
        
    except Exception as e:
        logger.error(f"Failed to create task file: {e}")
        
        # Quarantine the email data
        quarantine_item(
            item_type="email",
            item_content=f"From: {email_data.get('from')}\nSubject: {email_data.get('subject')}\n\n{email_data.get('body', '')}",
            source="gmail_watcher",
            reason="Failed to create task file",
            error=str(e),
            metadata={"message_id": message_id}
        )
        
        log_action(
            action_type="create_task",
            actor="gmail_watcher",
            target=message_id,
            parameters={},
            result="quarantined",
            error=str(e),
            quarantined=True
        )
        
        raise


# ============================================================================
# Main Watcher Loop
# ============================================================================

def process_emails():
    """Process new important emails with retry and error handling."""
    start_time = time.time()
    
    try:
        # Get Gmail service
        service = get_gmail_service()
        if not service:
            logger.warning("Gmail service not available - will retry next cycle")
            return False
        
        # List important unread messages
        messages = list_gmail_messages(service, GMAIL_QUERY, max_results=10)
        
        if not messages:
            logger.info("No new important emails")
            return True
        
        # Load processed IDs
        processed_ids = load_processed_ids()
        new_count = 0
        
        for msg in messages:
            message_id = msg['id']
            
            # Skip already processed
            if message_id in processed_ids:
                continue
            
            try:
                # Get full message
                raw_message = get_gmail_message(service, message_id)
                
                if not raw_message or 'raw' not in raw_message:
                    logger.warning(f"Message {message_id} has no raw content")
                    continue
                
                # Extract email data
                email_data = extract_email_data(raw_message['raw'])
                
                # Create task file
                create_task_file(email_data, message_id)
                
                # Mark as processed
                processed_ids.add(message_id)
                new_count += 1
                
                logger.info(f"Processed email from {email_data.get('from')}: {email_data.get('subject')}")
                
            except Exception as e:
                logger.error(f"Failed to process message {message_id}: {e}")
                
                # Try to quarantine
                try:
                    quarantine_item(
                        item_type="email",
                        item_content=f"Message ID: {message_id}",
                        source="gmail_watcher",
                        reason="Processing failed",
                        error=str(e),
                        metadata={"message_id": message_id}
                    )
                except:
                    pass
        
        # Save processed IDs
        save_processed_ids(processed_ids)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        log_action(
            action_type="process_cycle",
            actor="gmail_watcher",
            target="gmail_api",
            parameters={"query": GMAIL_QUERY},
            result="success",
            attempt=1,
            duration_ms=duration_ms
        )
        
        logger.info(f"Email processing complete: {new_count} new emails processed")
        return True
        
    except Exception as e:
        logger.error(f"Email processing cycle failed: {e}")
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        log_action(
            action_type="process_cycle",
            actor="gmail_watcher",
            target="gmail_api",
            parameters={},
            result="failure",
            error=str(e),
            duration_ms=duration_ms
        )
        
        return False


def main():
    """Main entry point - infinite polling loop."""
    logger.info("=" * 60)
    logger.info("GMAIL WATCHER (with retry handler) starting...")
    logger.info("=" * 60)
    logger.info(f"Poll interval: {POLL_INTERVAL}s")
    logger.info(f"Query: {GMAIL_QUERY}")
    logger.info(f"Max retries: {MAX_RETRIES}")
    logger.info("=" * 60)
    
    # Initial processing
    process_emails()
    
    # Continuous polling
    consecutive_failures = 0
    max_consecutive_failures = 10
    
    while True:
        try:
            time.sleep(POLL_INTERVAL)
            
            success = process_emails()
            
            if success:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logger.warning(f"Consecutive failures: {consecutive_failures}/{max_consecutive_failures}")
                
                if consecutive_failures >= max_consecutive_failures:
                    logger.error("Too many consecutive failures - entering degraded mode")
                    log_action(
                        action_type="degraded_mode",
                        actor="gmail_watcher",
                        target="system",
                        parameters={"consecutive_failures": consecutive_failures},
                        result="failure",
                        error="Max consecutive failures reached"
                    )
                    # Continue running but log the degraded state
                    consecutive_failures = 0  # Reset and continue
                    
        except KeyboardInterrupt:
            logger.info("Stopping Gmail Watcher...")
            break
        except Exception as e:
            logger.error(f"Watcher loop error: {e}")
            time.sleep(POLL_INTERVAL)
    
    # Final health check
    health = get_system_health()
    logger.info(f"Final health status: {health['summary']['success_rate']:.1f}% success rate")


if __name__ == "__main__":
    main()
