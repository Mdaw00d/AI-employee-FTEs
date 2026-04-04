#!/usr/bin/env python3
"""
Email MCP Server - JSON-RPC API for Gmail Operations
=====================================================
Provides a local MCP (Model Context Protocol) server for interacting with Gmail
via Google API. Used by AI agents for email operations.

Features:
- Send emails
- Create drafts
- Search/read emails
- Mark as read/unread
- Delete emails

Usage:
    python email_mcp.py

Server runs at: http://localhost:8000
Logs written to: Logs/email_mcp.log

Integration with Orchestrator:
    When email action needed, orchestrator calls:
    POST http://localhost:8000/rpc
    with method: send_email, create_draft, search_emails, etc.

Setup:
    1. Download credentials.json from Google Cloud Console
    2. Enable Gmail API
    3. First run will open browser for OAuth consent
    4. token.json will be created for subsequent runs
"""

import os
import sys
import io
import json
import logging
import base64
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from typing import Optional, Dict, Any, List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# Google API imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False
    print("WARNING: Google API libraries not installed.")
    print("Run: pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2")

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Configuration
SCOPES = ['https://www.googleapis.com/auth/gmail.send', 
          'https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/gmail.modify',
          'https://www.googleapis.com/auth/gmail.compose']

CREDENTIALS_FILE = "./credentials.json"
TOKEN_FILE = "./token_email.json"

# MCP Server Configuration
MCP_HOST = "localhost"
MCP_PORT = 8000  # Email MCP port

# Logging
LOG_DIR = Path("Logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "email_mcp.log"

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class GmailConnection:
    """Manages connection to Gmail via Google API."""

    def __init__(self, credentials_file: str, token_file: str):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self.creds = None

    def authenticate(self) -> bool:
        """Authenticate with Gmail API."""
        if not GMAIL_AVAILABLE:
            logger.error("Google API libraries not installed")
            return False

        try:
            creds = None

            # Load existing token
            if os.path.exists(self.token_file):
                try:
                    creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
                    logger.info(f"Loaded existing token from {self.token_file}")
                except Exception as e:
                    logger.warning(f"Failed to load token: {e}")
                    creds = None

            # Refresh or obtain new credentials
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        logger.info("Refreshing expired token...")
                        creds.refresh(Request())
                        logger.info("Token refreshed successfully")
                    except Exception as e:
                        logger.warning(f"Token refresh failed: {e}")
                        creds = None

                if not creds:
                    if not os.path.exists(self.credentials_file):
                        logger.error(f"Credentials file not found: {self.credentials_file}")
                        logger.error("Please download credentials.json from Google Cloud Console")
                        return False

                    try:
                        logger.info("Starting OAuth flow...")
                        flow = InstalledAppFlow.from_client_secrets_file(
                            self.credentials_file, SCOPES)
                        creds = flow.run_local_server(port=0, open_browser=False)
                        
                        # Save credentials
                        with open(self.token_file, 'w', encoding='utf-8') as f:
                            f.write(creds.to_json())
                        logger.info(f"Credentials saved to {self.token_file}")

                    except Exception as e:
                        logger.error(f"OAuth flow failed: {e}")
                        return False

            # Build Gmail service
            self.service = build('gmail', 'v1', credentials=creds)
            self.creds = creds
            logger.info("Gmail service initialized")
            return True

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    def send_email(self, to: str, subject: str, body: str, 
                   html: bool = False, cc: str = None, bcc: str = None,
                   attachments: List[str] = None) -> Dict:
        """
        Send an email.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body content
            html: If True, treat body as HTML
            cc: CC recipient(s)
            bcc: BCC recipient(s)
            attachments: List of file paths to attach

        Returns:
            Dict with message_id and status
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Not authenticated with Gmail")

        try:
            # Create message
            message = MIMEMultipart() if attachments else MIMEText('', 'html' if html else 'plain')
            message['to'] = to
            message['subject'] = subject

            if cc:
                message['cc'] = cc
            if bcc:
                message['bcc'] = bcc

            # Add body
            message.attach(MIMEText(body, 'html' if html else 'plain'))

            # Add attachments
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        part = MIMEBase('application', 'octet-stream')
                        with open(file_path, 'rb') as f:
                            part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename="{os.path.basename(file_path)}"'
                        )
                        message.attach(part)

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            # Send
            sent_message = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()

            logger.info(f"Email sent to {to}, message ID: {sent_message['id']}")
            return {
                'success': True,
                'message_id': sent_message['id'],
                'thread_id': sent_message.get('threadId'),
                'to': to,
                'subject': subject
            }

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            raise

    def create_draft(self, to: str, subject: str, body: str,
                     html: bool = False, cc: str = None) -> Dict:
        """
        Create an email draft.

        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body content
            html: If True, treat body as HTML
            cc: CC recipient(s)

        Returns:
            Dict with draft_id and message details
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Not authenticated with Gmail")

        try:
            # Create message
            message = MIMEText(body, 'html' if html else 'plain')
            message['to'] = to
            message['subject'] = subject
            if cc:
                message['cc'] = cc

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            # Create draft
            draft = self.service.users().drafts().create(
                userId='me',
                body={'message': {'raw': raw_message}}
            ).execute()

            logger.info(f"Draft created, ID: {draft['id']}")
            return {
                'success': True,
                'draft_id': draft['id'],
                'message_id': draft['message']['id'],
                'to': to,
                'subject': subject
            }

        except Exception as e:
            logger.error(f"Failed to create draft: {e}")
            raise

    def search_emails(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Search for emails.

        Args:
            query: Gmail search query (e.g., "is:unread", "from:someone @example.com")
            max_results: Maximum number of results

        Returns:
            List of email summaries
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Not authenticated with Gmail")

        try:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()

            messages = results.get('messages', [])
            email_list = []

            for msg in messages:
                email_data = self.get_email(msg['id'])
                if email_data:
                    email_list.append(email_data)

            logger.info(f"Found {len(email_list)} emails matching query: {query}")
            return email_list

        except Exception as e:
            logger.error(f"Failed to search emails: {e}")
            raise

    def get_email(self, message_id: str) -> Dict:
        """
        Get full email details.

        Args:
            message_id: Gmail message ID

        Returns:
            Dict with email details
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Not authenticated with Gmail")

        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()

            # Extract headers
            headers = {h['name']: h['value'] for h in message['payload']['headers']}

            # Extract body
            body = self._extract_body(message['payload'])

            return {
                'id': message['id'],
                'thread_id': message['threadId'],
                'from': headers.get('From', ''),
                'to': headers.get('To', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'snippet': message.get('snippet', ''),
                'body': body,
                'labels': message.get('labelIds', [])
            }

        except Exception as e:
            logger.error(f"Failed to get email: {e}")
            raise

    def _extract_body(self, payload: Dict) -> str:
        """Extract body text from email payload."""
        if 'parts' in payload:
            # Multipart message - prefer plain text
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        return base64.urlsafe_b64decode(
                            part['body']['data'] + '==='  # Add padding
                        ).decode('utf-8', errors='replace')
            # Fallback to HTML
            for part in payload['parts']:
                if part['mimeType'] == 'text/html':
                    if 'data' in part['body']:
                        return base64.urlsafe_b64decode(
                            part['body']['data'] + '==='
                        ).decode('utf-8', errors='replace')
        elif 'body' in payload and 'data' in payload['body']:
            return base64.urlsafe_b64decode(
                payload['body']['data'] + '==='
            ).decode('utf-8', errors='replace')
        return ''

    def mark_as_read(self, message_id: str) -> Dict:
        """
        Mark an email as read.

        Args:
            message_id: Gmail message ID

        Returns:
            Dict with status
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Not authenticated with Gmail")

        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()

            logger.info(f"Marked message {message_id} as read")
            return {'success': True, 'message_id': message_id, 'status': 'read'}

        except Exception as e:
            logger.error(f"Failed to mark as read: {e}")
            raise

    def mark_as_unread(self, message_id: str) -> Dict:
        """
        Mark an email as unread.

        Args:
            message_id: Gmail message ID

        Returns:
            Dict with status
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Not authenticated with Gmail")

        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': ['UNREAD']}
            ).execute()

            logger.info(f"Marked message {message_id} as unread")
            return {'success': True, 'message_id': message_id, 'status': 'unread'}

        except Exception as e:
            logger.error(f"Failed to mark as unread: {e}")
            raise

    def delete_email(self, message_id: str) -> Dict:
        """
        Delete an email (moves to trash).

        Args:
            message_id: Gmail message ID

        Returns:
            Dict with status
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Not authenticated with Gmail")

        try:
            self.service.users().messages().delete(
                userId='me',
                id=message_id
            ).execute()

            logger.info(f"Deleted message {message_id}")
            return {'success': True, 'message_id': message_id, 'status': 'deleted'}

        except Exception as e:
            logger.error(f"Failed to delete email: {e}")
            raise

    def send_reply(self, original_message_id: str, body: str,
                   html: bool = False) -> Dict:
        """
        Send a reply to an existing email.

        Args:
            original_message_id: ID of the message to reply to
            body: Reply body content
            html: If True, treat body as HTML

        Returns:
            Dict with message_id and status
        """
        if not self.service:
            if not self.authenticate():
                raise Exception("Not authenticated with Gmail")

        try:
            # Get original message for thread info
            original = self.service.users().messages().get(
                userId='me',
                id=original_message_id,
                format='metadata',
                metadataHeaders=['From', 'To', 'Subject']
            ).execute()

            headers = {h['name']: h['value'] for h in original['payload']['headers']}
            original_subject = headers.get('Subject', '')
            original_from = headers.get('From', '')

            # Create reply message
            message = MIMEText(body, 'html' if html else 'plain')
            message['to'] = original_from
            message['subject'] = f"Re: {original_subject}"
            message['In-Reply-To'] = original_message_id
            message['References'] = original_message_id

            # Encode and send
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            sent_message = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message, 'threadId': original['threadId']}
            ).execute()

            logger.info(f"Reply sent to thread {original['threadId']}")
            return {
                'success': True,
                'message_id': sent_message['id'],
                'thread_id': sent_message.get('threadId'),
                'in_reply_to': original_message_id
            }

        except Exception as e:
            logger.error(f"Failed to send reply: {e}")
            raise


class MCPServerHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for MCP JSON-RPC API."""

    gmail: Optional[GmailConnection] = None
    demo_mode: bool = False

    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.info(f"HTTP: {args[0]}")

    def send_json_response(self, data: Dict, status: int = 200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def send_error_response(self, message: str, code: int = -32000):
        """Send JSON-RPC error response."""
        self.send_json_response({
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message
            },
            "id": None
        }, status=400)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        """Handle JSON-RPC POST requests."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')

            try:
                request = json.loads(body)
            except json.JSONDecodeError as e:
                self.send_error_response(f"Invalid JSON: {e}")
                return

            if not isinstance(request, dict):
                self.send_error_response("Request must be a JSON object")
                return

            method = request.get('method')
            params = request.get('params', {})
            request_id = request.get('id')

            if not method:
                self.send_error_response("Missing 'method' in request")
                return

            logger.info(f"RPC Method: {method}")
            logger.debug(f"Params: {params}")

            result = self.handle_method(method, params)

            response = {
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id
            }
            self.send_json_response(response)

        except Exception as e:
            logger.exception(f"Error handling request: {e}")
            self.send_error_response(str(e))

    def handle_method(self, method: str, params: Dict) -> Any:
        """Route JSON-RPC method to appropriate handler."""

        methods = {
            # Email Operations
            "send_email": self.send_email,
            "create_draft": self.create_draft,
            "send_reply": self.send_reply,
            "search_emails": self.search_emails,
            "get_email": self.get_email,
            "mark_as_read": self.mark_as_read,
            "mark_as_unread": self.mark_as_unread,
            "delete_email": self.delete_email,

            # System Operations
            "health_check": self.health_check,
            "get_version": self.get_version,
            "authenticate": self.authenticate,
        }

        if method not in methods:
            raise Exception(f"Unknown method: {method}")

        return methods[method](params)

    # ==================== Email Methods ====================

    def send_email(self, params: Dict) -> Dict:
        """
        Send an email.

        Params:
            to: str - Recipient email address (required)
            subject: str - Email subject (required)
            body: str - Email body content (required)
            html: bool - Treat body as HTML (default False)
            cc: str - CC recipient(s)
            bcc: str - BCC recipient(s)
            attachments: list - List of file paths to attach

        Returns:
            success: bool
            message_id: str
            thread_id: str
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.gmail:
            logger.info("DEMO MODE: Returning mock send_email response")
            return {
                'success': True,
                'message_id': 'demo_msg_' + datetime.now().strftime('%Y%m%d%H%M%S'),
                'thread_id': 'demo_thread_001',
                'to': params.get('to', 'unknown @example.com'),
                'subject': params.get('subject', 'No Subject'),
                'demo_mode': True,
                'message': 'Gmail not authenticated. This is a mock response.'
            }

        to = params.get('to')
        subject = params.get('subject')
        body = params.get('body')

        if not to or not subject or not body:
            raise Exception("to, subject, and body are required")

        return MCPServerHandler.gmail.send_email(
            to=to,
            subject=subject,
            body=body,
            html=params.get('html', False),
            cc=params.get('cc'),
            bcc=params.get('bcc'),
            attachments=params.get('attachments', [])
        )

    def create_draft(self, params: Dict) -> Dict:
        """
        Create an email draft.

        Params:
            to: str - Recipient email address (required)
            subject: str - Email subject (required)
            body: str - Email body content (required)
            html: bool - Treat body as HTML (default False)
            cc: str - CC recipient(s)

        Returns:
            success: bool
            draft_id: str
            message_id: str
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.gmail:
            logger.info("DEMO MODE: Returning mock create_draft response")
            return {
                'success': True,
                'draft_id': 'demo_draft_' + datetime.now().strftime('%Y%m%d%H%M%S'),
                'message_id': 'demo_msg_001',
                'to': params.get('to', 'unknown @example.com'),
                'subject': params.get('subject', 'No Subject'),
                'demo_mode': True,
                'message': 'Gmail not authenticated. This is a mock response.'
            }

        to = params.get('to')
        subject = params.get('subject')
        body = params.get('body')

        if not to or not subject or not body:
            raise Exception("to, subject, and body are required")

        return MCPServerHandler.gmail.create_draft(
            to=to,
            subject=subject,
            body=body,
            html=params.get('html', False),
            cc=params.get('cc')
        )

    def send_reply(self, params: Dict) -> Dict:
        """
        Send a reply to an existing email.

        Params:
            original_message_id: str - ID of message to reply to (required)
            body: str - Reply body content (required)
            html: bool - Treat body as HTML (default False)

        Returns:
            success: bool
            message_id: str
            thread_id: str
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.gmail:
            logger.info("DEMO MODE: Returning mock send_reply response")
            return {
                'success': True,
                'message_id': 'demo_reply_' + datetime.now().strftime('%Y%m%d%H%M%S'),
                'thread_id': 'demo_thread_001',
                'demo_mode': True,
                'message': 'Gmail not authenticated. This is a mock response.'
            }

        original_message_id = params.get('original_message_id')
        body = params.get('body')

        if not original_message_id or not body:
            raise Exception("original_message_id and body are required")

        return MCPServerHandler.gmail.send_reply(
            original_message_id=original_message_id,
            body=body,
            html=params.get('html', False)
        )

    def search_emails(self, params: Dict) -> List[Dict]:
        """
        Search for emails.

        Params:
            query: str - Gmail search query (required)
            max_results: int - Maximum results (default 10)

        Returns:
            List of email summaries
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.gmail:
            logger.info("DEMO MODE: Returning mock search_emails response")
            return [
                {
                    'id': 'demo_msg_001',
                    'thread_id': 'demo_thread_001',
                    'from': 'sender @example.com',
                    'to': 'me @example.com',
                    'subject': 'Demo Email 1',
                    'date': datetime.now().isoformat(),
                    'snippet': 'This is a demo email snippet...',
                    'demo_mode': True
                }
            ]

        query = params.get('query')
        if not query:
            raise Exception("query is required")

        return MCPServerHandler.gmail.search_emails(
            query=query,
            max_results=params.get('max_results', 10)
        )

    def get_email(self, params: Dict) -> Dict:
        """
        Get full email details.

        Params:
            message_id: str - Gmail message ID (required)

        Returns:
            Dict with email details
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.gmail:
            logger.info("DEMO MODE: Returning mock get_email response")
            return {
                'id': 'demo_msg_001',
                'thread_id': 'demo_thread_001',
                'from': 'sender @example.com',
                'to': 'me @example.com',
                'subject': 'Demo Email',
                'date': datetime.now().isoformat(),
                'snippet': 'Demo snippet...',
                'body': 'This is a demo email body.',
                'demo_mode': True
            }

        message_id = params.get('message_id')
        if not message_id:
            raise Exception("message_id is required")

        return MCPServerHandler.gmail.get_email(message_id)

    def mark_as_read(self, params: Dict) -> Dict:
        """
        Mark an email as read.

        Params:
            message_id: str - Gmail message ID (required)

        Returns:
            Dict with status
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.gmail:
            logger.info("DEMO MODE: Returning mock mark_as_read response")
            return {
                'success': True,
                'message_id': params.get('message_id', 'demo_msg_001'),
                'status': 'read',
                'demo_mode': True
            }

        message_id = params.get('message_id')
        if not message_id:
            raise Exception("message_id is required")

        return MCPServerHandler.gmail.mark_as_read(message_id)

    def mark_as_unread(self, params: Dict) -> Dict:
        """
        Mark an email as unread.

        Params:
            message_id: str - Gmail message ID (required)

        Returns:
            Dict with status
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.gmail:
            logger.info("DEMO MODE: Returning mock mark_as_unread response")
            return {
                'success': True,
                'message_id': params.get('message_id', 'demo_msg_001'),
                'status': 'unread',
                'demo_mode': True
            }

        message_id = params.get('message_id')
        if not message_id:
            raise Exception("message_id is required")

        return MCPServerHandler.gmail.mark_as_unread(message_id)

    def delete_email(self, params: Dict) -> Dict:
        """
        Delete an email (moves to trash).

        Params:
            message_id: str - Gmail message ID (required)

        Returns:
            Dict with status
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.gmail:
            logger.info("DEMO MODE: Returning mock delete_email response")
            return {
                'success': True,
                'message_id': params.get('message_id', 'demo_msg_001'),
                'status': 'deleted',
                'demo_mode': True
            }

        message_id = params.get('message_id')
        if not message_id:
            raise Exception("message_id is required")

        return MCPServerHandler.gmail.delete_email(message_id)

    # ==================== System Methods ====================

    def health_check(self, params: Dict) -> Dict:
        """Check server health."""
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'gmail_authenticated': MCPServerHandler.gmail is not None and MCPServerHandler.gmail.service is not None,
            'demo_mode': MCPServerHandler.demo_mode
        }

    def get_version(self, params: Dict) -> Dict:
        """Get server version info."""
        return {
            'name': 'Email MCP Server',
            'version': '1.0.0',
            'port': MCP_PORT,
            'description': 'JSON-RPC API for Gmail operations'
        }

    def authenticate(self, params: Dict) -> Dict:
        """
        Authenticate with Gmail API.

        Params:
            force: bool - Force re-authentication (default False)

        Returns:
            Dict with authentication status
        """
        force = params.get('force', False)

        if MCPServerHandler.gmail and MCPServerHandler.gmail.service and not force:
            return {
                'success': True,
                'status': 'already_authenticated',
                'message': 'Already authenticated with Gmail'
            }

        MCPServerHandler.gmail = GmailConnection(CREDENTIALS_FILE, TOKEN_FILE)
        success = MCPServerHandler.gmail.authenticate()

        return {
            'success': success,
            'status': 'authenticated' if success else 'authentication_failed',
            'message': 'Successfully authenticated with Gmail' if success else 'Authentication failed'
        }


def run_server(host: str = MCP_HOST, port: int = MCP_PORT, demo_mode: bool = False):
    """Run the MCP server."""
    MCPServerHandler.demo_mode = demo_mode

    if not demo_mode:
        logger.info("Initializing Gmail connection...")
        MCPServerHandler.gmail = GmailConnection(CREDENTIALS_FILE, TOKEN_FILE)
        # Don't fail if auth fails - will work in demo mode
        MCPServerHandler.gmail.authenticate()

    server = HTTPServer((host, port), MCPServerHandler)
    logger.info(f"Email MCP Server starting at http://{host}:{port}")
    logger.info(f"Demo mode: {demo_mode}")
    logger.info(f"Logs: {LOG_FILE}")
    logger.info("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        server.shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Email MCP Server - Gmail API')
    parser.add_argument('--host', default=MCP_HOST, help=f'Host to bind to (default: {MCP_HOST})')
    parser.add_argument('--port', type=int, default=MCP_PORT, help=f'Port to bind to (default: {MCP_PORT})')
    parser.add_argument('--demo', action='store_true', help='Run in demo mode (no real API calls)')
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, demo_mode=args.demo)
