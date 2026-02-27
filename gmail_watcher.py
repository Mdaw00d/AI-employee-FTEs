"""
Gmail Watcher - Monitors Gmail for important unread emails requiring action.

This script polls the Gmail API every 120 seconds for new important emails
and creates task files in Needs_Action/ for processing.

================================================================================
FIRST RUN SETUP
================================================================================
1. Ensure credentials.json (Gmail OAuth) is in the project root
2. Run: python gmail_watcher.py
3. Browser will open - complete OAuth consent
4. token.json will be created automatically for subsequent runs

================================================================================
PERSISTENT OPERATION
================================================================================
Using PM2:
    pm2 start gmail_watcher.py --interpreter python --name gmail-watcher

Using Python directly:
    python gmail_watcher.py

To stop:
    pm2 stop gmail-watcher
    pm2 delete gmail-watcher

================================================================================
DEPENDENCIES
================================================================================
    pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2

================================================================================
"""

import os
import sys
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

# ============================================================================
# Configuration
# ============================================================================

# Gmail API SCOPES - readonly for watching
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Polling interval in seconds
POLL_INTERVAL = 120

# Maximum retries before giving up
MAX_RETRIES = 5
BASE_BACKOFF = 10  # seconds

# Query for important unread emails
# You can customize this query as needed
GMAIL_QUERY = 'is:unread is:important'

# Alternative queries you might use:
# GMAIL_QUERY = 'is:unread in:inbox'  # All unread inbox emails
# GMAIL_QUERY = 'is:unread from:important@client.com'  # Specific sender
# GMAIL_QUERY = 'is:unread subject:(urgent OR invoice OR proposal)'  # Specific subjects

# File paths
CREDENTIALS_FILE = './credentials.json'
TOKEN_FILE = './token.json'
PROCESSED_IDS_FILE = './processed_ids.pkl'
NEEDS_ACTION_DIR = './Needs_Action'
LOGS_DIR = './Logs'

# Ensure directories exist
for directory in [NEEDS_ACTION_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'gmail_watcher.log'), encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ============================================================================
# Gmail Authentication
# ============================================================================

def get_gmail_credentials():
    """
    Authenticate with Gmail API using OAuth2.
    
    Returns:
        Credentials object or None if authentication fails
    """
    creds = None
    
    # Load existing token if available
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            logging.info(f"Loaded existing token from {TOKEN_FILE}")
        except Exception as e:
            logging.warning(f"Failed to load token: {e}")
            creds = None
    
    # Refresh or obtain new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logging.info("Refreshing expired token...")
                creds.refresh(Request())
                logging.info("Token refreshed successfully")
            except Exception as e:
                logging.warning(f"Token refresh failed: {e}")
                creds = None
        
        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                logging.error(f"Credentials file not found: {CREDENTIALS_FILE}")
                logging.error("Please download credentials.json from Google Cloud Console")
                logging.error("Go to: https://console.cloud.google.com/apis/credentials")
                return None
            
            try:
                logging.info("Starting OAuth flow...")
                logging.info("Opening browser for authentication...")
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0, open_browser=True)
                
                # Save credentials for future use
                with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
                    f.write(creds.to_json())
                logging.info(f"Credentials saved to {TOKEN_FILE}")
                
            except Exception as e:
                logging.error(f"OAuth flow failed: {e}")
                return None
    
    return creds


# ============================================================================
# Processed IDs Management
# ============================================================================

def load_processed_ids():
    """
    Load set of already processed message IDs from pickle file.
    
    Returns:
        Set of message ID strings
    """
    if os.path.exists(PROCESSED_IDS_FILE):
        try:
            with open(PROCESSED_IDS_FILE, 'rb') as f:
                processed_ids = pickle.load(f)
            logging.info(f"Loaded {len(processed_ids)} processed message IDs")
            return processed_ids
        except Exception as e:
            logging.warning(f"Failed to load processed IDs: {e}")
            return set()
    return set()


def save_processed_ids(processed_ids: set):
    """
    Save processed message IDs to pickle file for persistence.
    
    Args:
        processed_ids: Set of message ID strings to save
    """
    try:
        with open(PROCESSED_IDS_FILE, 'wb') as f:
            pickle.dump(processed_ids, f)
        logging.info(f"Saved {len(processed_ids)} processed message IDs")
    except Exception as e:
        logging.error(f"Failed to save processed IDs: {e}")


# ============================================================================
# Email Processing
# ============================================================================

def decode_mime_header(header_value):
    """
    Decode MIME-encoded header values (handles UTF-8, base64, quoted-printable).
    
    Args:
        header_value: Raw header value string
        
    Returns:
        Decoded string
    """
    if not header_value:
        return ""
    
    try:
        # Try to decode using email.header
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
    """
    Decode URL-safe base64 data (Gmail API format).
    
    Args:
        data: Base64 URL-safe encoded string
        
    Returns:
        Decoded bytes
    """
    # Add padding if needed
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    
    # Convert from URL-safe to standard base64
    data = data.replace('-', '+').replace('_', '/')
    
    return base64.b64decode(data)


def extract_email_data(raw_message: str) -> dict:
    """
    Extract email data from raw Gmail message.
    
    Args:
        raw_message: Raw RFC822 message string (base64 encoded)
        
    Returns:
        Dictionary with email fields
    """
    try:
        # Decode the raw message
        message_bytes = decode_base64_url_safe(raw_message)
        msg = message_from_bytes(message_bytes)
        
        # Extract headers
        email_from = decode_mime_header(msg.get('From', ''))
        subject = decode_mime_header(msg.get('Subject', ''))
        date = decode_mime_header(msg.get('Date', ''))
        to = decode_mime_header(msg.get('To', ''))
        
        # Extract body (prefer plain text, fallback to HTML)
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get_content_disposition())
                
                # Skip attachments
                if 'attachment' in content_disposition:
                    continue
                
                if content_type == 'text/plain':
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        body = part.get_payload(decode=True).decode(charset, errors='replace')
                        break
                    except Exception:
                        continue
            # Fallback to HTML if no plain text
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == 'text/html':
                        try:
                            charset = part.get_content_charset() or 'utf-8'
                            body = part.get_payload(decode=True).decode(charset, errors='replace')
                            # Strip HTML tags for snippet
                            import re
                            body = re.sub(r'<[^>]+>', '', body)
                            break
                        except Exception:
                            continue
        else:
            try:
                charset = msg.get_content_charset() or 'utf-8'
                body = msg.get_payload(decode=True).decode(charset, errors='replace')
            except Exception:
                body = msg.get_payload()
        
        # Clean up body
        body = body.strip()
        snippet = body[:500] + '...' if len(body) > 500 else body
        
        return {
            'from': email_from,
            'to': to,
            'subject': subject,
            'date': date,
            'body': body,
            'snippet': snippet
        }
        
    except Exception as e:
        logging.error(f"Failed to extract email data: {e}")
        return {
            'from': 'Unknown',
            'to': '',
            'subject': 'Error decoding email',
            'date': '',
            'body': '',
            'snippet': f'Error: {str(e)}'
        }


def create_needs_action_file(email_data: dict, message_id: str) -> str:
    """
    Create a Needs_Action markdown file for the email.
    
    Args:
        email_data: Dictionary with email fields
        message_id: Gmail message ID
        
    Returns:
        Path to created file
    """
    os.makedirs(NEEDS_ACTION_DIR, exist_ok=True)
    
    # Generate filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Clean message_id for filename (remove special chars)
    clean_msg_id = message_id.replace('/', '_').replace('+', '_')
    filename = f"EMAIL_{clean_msg_id}_{timestamp}.md"
    filepath = os.path.join(NEEDS_ACTION_DIR, filename)
    
    # Format received date
    received_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if email_data.get('date'):
        try:
            from email.utils import parsedate_to_datetime
            parsed_date = parsedate_to_datetime(email_data['date'])
            received_date = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            pass
    
    # Generate suggested actions
    suggested_actions = """- [ ] Reply
- [ ] Archive
- [ ] Flag
- [ ] Forward"""
    
    # Check for priority indicators in subject/body
    subject_lower = email_data.get('subject', '').lower()
    body_lower = email_data.get('body', '').lower()
    full_content = subject_lower + body_lower
    
    priority = 'high'  # Default high since we're watching important emails
    
    # Adjust priority based on content
    urgent_keywords = ['urgent', 'asap', 'immediately', 'emergency', 'critical']
    if any(kw in full_content for kw in urgent_keywords):
        priority = 'high'
        suggested_actions = "- [ ] **URGENT** - Respond immediately\n" + suggested_actions
    
    invoice_keywords = ['invoice', 'payment', 'billing', 'receipt', 'due']
    if any(kw in full_content for kw in invoice_keywords):
        suggested_actions += "\n- [ ] Process payment/invoice\n- [ ] Forward to accounting"
    
    support_keywords = ['support', 'help', 'issue', 'problem', 'error', 'bug']
    if any(kw in full_content for kw in support_keywords):
        suggested_actions += "\n- [ ] Investigate issue\n- [ ] Create support ticket"
    
    file_content = f"""---
type: email
from: {email_data['from']}
subject: {email_data['subject']}
received: {received_date}
priority: {priority}
status: pending
message_id: {message_id}
to: {email_data['to']}
---

# Email Requiring Action

## From
**{email_data['from']}**

## Subject
{email_data['subject']}

## Received
{received_date}

## Message
{email_data['snippet']}

## Full Headers
- **From:** {email_data['from']}
- **To:** {email_data['to']}
- **Subject:** {email_data['subject']}
- **Date:** {email_data['date']}

## Suggested Actions
{suggested_actions}

## Notes
_Add any additional context or actions below_

"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(file_content)
    
    logging.info(f"Created task file: {filename}")
    return filepath


# ============================================================================
# Gmail API Operations
# ============================================================================

def fetch_unread_emails(service, query: str = None) -> list:
    """
    Fetch unread emails from Gmail.
    
    Args:
        service: Gmail API service object
        query: Gmail search query
        
    Returns:
        List of message dicts with id and raw data
    """
    if query is None:
        query = GMAIL_QUERY
    
    messages = []
    
    try:
        # Search for messages
        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=20  # Limit to 20 at a time
        ).execute()
        
        message_list = results.get('messages', [])
        
        if not message_list:
            logging.info("No unread important emails found")
            return messages
        
        logging.info(f"Found {len(message_list)} unread important email(s)")
        
        # Get full message data for each
        for msg in message_list:
            try:
                message = service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='raw'
                ).execute()
                
                messages.append({
                    'id': message['id'],
                    'threadId': message['threadId'],
                    'raw': message['raw'],
                    'internalDate': message.get('internalDate', '')
                })
            except Exception as e:
                logging.error(f"Failed to fetch message {msg['id']}: {e}")
                continue
        
    except HttpError as error:
        logging.error(f"Gmail API error: {error}")
        if error.resp.status == 401:
            logging.error("Authentication error - credentials may need refresh")
    
    return messages


def process_email(message_data: dict, processed_ids: set) -> bool:
    """
    Process a single email message.
    
    Args:
        message_data: Dict with message id and raw data
        processed_ids: Set of already processed message IDs
        
    Returns:
        True if processed successfully, False otherwise
    """
    message_id = message_data['id']
    
    # Skip if already processed
    if message_id in processed_ids:
        logging.debug(f"Message {message_id} already processed, skipping")
        return False
    
    try:
        # Extract email data
        email_data = extract_email_data(message_data['raw'])
        
        logging.info(f"Processing email from '{email_data['from']}': {email_data['subject']}")
        
        # Create Needs_Action file
        create_needs_action_file(email_data, message_id)
        
        # Mark as processed
        processed_ids.add(message_id)
        
        return True
        
    except Exception as e:
        logging.error(f"Failed to process message {message_id}: {e}")
        return False


# ============================================================================
# Main Watcher Loop
# ============================================================================

def main():
    """Main Gmail watcher loop."""
    logging.info("=" * 60)
    logging.info("Gmail Watcher starting...")
    logging.info(f"Query: {GMAIL_QUERY}")
    logging.info(f"Poll interval: {POLL_INTERVAL} seconds")
    logging.info(f"Credentials: {CREDENTIALS_FILE}")
    logging.info(f"Token: {TOKEN_FILE}")
    logging.info("=" * 60)
    
    # Load processed IDs
    processed_ids = load_processed_ids()
    
    # Authenticate
    logging.info("Authenticating with Gmail...")
    creds = get_gmail_credentials()
    
    if not creds:
        logging.error("Failed to authenticate. Please ensure credentials.json exists.")
        logging.error("Run this script again after adding credentials.")
        return
    
    # Build Gmail service
    try:
        service = build('gmail', 'v1', credentials=creds)
        logging.info("Gmail service initialized")
    except Exception as e:
        logging.error(f"Failed to build Gmail service: {e}")
        return
    
    retry_count = 0
    
    logging.info("Gmail Watcher is now monitoring...")
    logging.info(f"Watching for: {GMAIL_QUERY}")
    
    while True:
        try:
            # Fetch unread emails
            messages = fetch_unread_emails(service)
            
            if messages:
                logging.info(f"Processing {len(messages)} new email(s)...")
                
                for msg in messages:
                    if process_email(msg, processed_ids):
                        logging.info(f"Successfully processed message: {msg['id']}")
                
                # Save processed IDs after each batch
                save_processed_ids(processed_ids)
            else:
                logging.debug("No new emails to process")
            
            # Reset retry count on success
            retry_count = 0
            
        except Exception as e:
            retry_count += 1
            logging.error(f"Error during polling (attempt {retry_count}/{MAX_RETRIES}): {e}")
            
            # Exponential backoff with jitter
            if retry_count <= MAX_RETRIES:
                backoff_time = min(BASE_BACKOFF * (2 ** (retry_count - 1)), 300)
                jitter = random.uniform(0, backoff_time * 0.1)
                total_wait = backoff_time + jitter
                
                logging.info(f"Retrying in {total_wait:.1f} seconds...")
                time.sleep(total_wait)
                
                # Try to re-authenticate if needed
                if retry_count >= 3:
                    logging.info("Attempting to refresh credentials...")
                    creds = get_gmail_credentials()
                    if creds:
                        try:
                            service = build('gmail', 'v1', credentials=creds)
                            logging.info("Service re-initialized")
                        except Exception as reinit_error:
                            logging.error(f"Re-initialization failed: {reinit_error}")
            else:
                logging.error("Max retries exceeded. Continuing with next poll...")
                retry_count = 0
        
        # Sleep until next poll
        logging.debug(f"Next poll in {POLL_INTERVAL} seconds")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Gmail Watcher stopped by user")
    except Exception as e:
        logging.critical(f"Fatal error: {e}")
        raise
