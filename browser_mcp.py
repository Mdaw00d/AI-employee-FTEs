#!/usr/bin/env python3
"""
Browser MCP Server - JSON-RPC API for General Browser Actions
==============================================================
Provides a local MCP server for general browser automation tasks.
Uses Playwright for browser automation.

Features:
- Navigate to URLs
- Fill forms and submit
- Click elements
- Extract page content
- Take screenshots
- Handle payment portals
- Download files
- Execute JavaScript

Usage:
    python browser_mcp.py

Server runs at: http://localhost:8002
Logs written to: Logs/browser_mcp.log

Integration with Orchestrator:
    When browser action needed, orchestrator calls:
    POST http://localhost:8002/rpc
    with method: navigate, fill_form, click, screenshot, etc.

Session Management:
    Sessions stored in ./browser_sessions/ directory
    Supports persistent sessions for authenticated sites
"""

import os
import sys
import io
import json
import logging
import time
import base64
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# MCP Server Configuration
MCP_HOST = "localhost"
MCP_PORT = 8002  # Browser MCP port

# Logging
LOG_DIR = Path("Logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "browser_mcp.log"

# Session directories
SESSION_DIR = Path("browser_sessions")
SESSION_DIR.mkdir(exist_ok=True)

# Screenshots directory
SCREENSHOTS_DIR = Path("Screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class BrowserSession:
    """Manages a browser session for automation tasks."""

    def __init__(self, session_id: str = None, headless: bool = False):
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._initialized = False

    def start(self, user_data_dir: str = None) -> bool:
        """
        Start the browser session.

        Args:
            user_data_dir: Optional directory for persistent session data

        Returns:
            True if successful
        """
        try:
            from playwright.sync_api import sync_playwright

            self.playwright = sync_playwright().start()

            browser_args = [
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
            ]

            if user_data_dir:
                # Persistent context for logged-in sessions
                self.browser = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=self.headless,
                    viewport={"width": 1280, "height": 720},
                    args=browser_args
                )
                self.context = self.browser
                if self.browser.pages:
                    self.page = self.browser.pages[0]
                else:
                    self.page = self.browser.new_page()
            else:
                # Regular browser
                self.browser = self.playwright.chromium.launch(
                    headless=self.headless,
                    args=browser_args
                )
                self.context = self.browser.new_context(
                    viewport={"width": 1280, "height": 720}
                )
                self.page = self.context.new_page()

            self._initialized = True
            logger.info(f"Browser session started: {self.session_id}")
            return True

        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install")
            return False
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            return False

    def navigate(self, url: str, wait_until: str = 'networkidle', timeout: int = 60000) -> Dict:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: When to consider navigation complete
                       ('load', 'domcontentloaded', 'networkidle', 'commit')
            timeout: Navigation timeout in ms

        Returns:
            Dict with navigation status
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        try:
            logger.info(f"Navigating to: {url}")
            self.page.goto(url, wait_until=wait_until, timeout=timeout)
            
            return {
                'success': True,
                'url': self.page.url,
                'title': self.page.title(),
                'status': 'loaded'
            }
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return {'success': False, 'error': str(e)}

    def fill(self, selector: str, value: str) -> Dict:
        """
        Fill a form field.

        Args:
            selector: CSS selector for the input field
            value: Value to fill

        Returns:
            Dict with fill status
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        try:
            logger.info(f"Filling {selector} with value")
            element = self.page.wait_for_selector(selector, timeout=10000)
            element.fill(value)
            
            return {
                'success': True,
                'selector': selector,
                'status': 'filled'
            }
        except Exception as e:
            logger.error(f"Fill failed: {e}")
            return {'success': False, 'error': str(e)}

    def click(self, selector: str, timeout: int = 10000) -> Dict:
        """
        Click an element.

        Args:
            selector: CSS selector for the element
            timeout: Wait timeout in ms

        Returns:
            Dict with click status
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        try:
            logger.info(f"Clicking: {selector}")
            element = self.page.wait_for_selector(selector, timeout=timeout)
            element.scroll_into_view_if_needed()
            element.click()
            
            return {
                'success': True,
                'selector': selector,
                'status': 'clicked'
            }
        except Exception as e:
            logger.error(f"Click failed: {e}")
            return {'success': False, 'error': str(e)}

    def get_text(self, selector: str) -> Dict:
        """
        Get text content of an element.

        Args:
            selector: CSS selector for the element

        Returns:
            Dict with text content
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        try:
            element = self.page.wait_for_selector(selector, timeout=5000)
            text = element.inner_text()
            
            return {
                'success': True,
                'selector': selector,
                'text': text
            }
        except Exception as e:
            logger.error(f"Get text failed: {e}")
            return {'success': False, 'error': str(e)}

    def get_html(self, selector: str = None) -> Dict:
        """
        Get HTML content of page or element.

        Args:
            selector: Optional CSS selector (returns full page HTML if not provided)

        Returns:
            Dict with HTML content
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        try:
            if selector:
                element = self.page.wait_for_selector(selector, timeout=5000)
                html = element.inner_html()
            else:
                html = self.page.content()
            
            return {
                'success': True,
                'selector': selector or 'page',
                'html': html
            }
        except Exception as e:
            logger.error(f"Get HTML failed: {e}")
            return {'success': False, 'error': str(e)}

    def screenshot(self, path: str = None, full_page: bool = False) -> Dict:
        """
        Take a screenshot.

        Args:
            path: Optional file path (auto-generated if not provided)
            full_page: If True, capture full scrollable page

        Returns:
            Dict with screenshot info
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        try:
            if not path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                path = str(SCREENSHOTS_DIR / f"screenshot_{timestamp}.png")

            self.page.screenshot(path=path, full_page=full_page)
            logger.info(f"Screenshot saved: {path}")
            
            return {
                'success': True,
                'path': path,
                'status': 'captured'
            }
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return {'success': False, 'error': str(e)}

    def execute_script(self, script: str) -> Dict:
        """
        Execute JavaScript code.

        Args:
            script: JavaScript code to execute

        Returns:
            Dict with execution result
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        try:
            result = self.page.evaluate(script)
            
            return {
                'success': True,
                'result': result
            }
        except Exception as e:
            logger.error(f"Script execution failed: {e}")
            return {'success': False, 'error': str(e)}

    def wait_for_selector(self, selector: str, timeout: int = 30000, 
                          state: str = 'visible') -> Dict:
        """
        Wait for an element to appear.

        Args:
            selector: CSS selector to wait for
            timeout: Wait timeout in ms
            state: Expected state ('visible', 'hidden', 'attached', 'detached')

        Returns:
            Dict with wait status
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        try:
            self.page.wait_for_selector(selector, timeout=timeout, state=state)
            
            return {
                'success': True,
                'selector': selector,
                'state': state,
                'status': 'found'
            }
        except Exception as e:
            logger.error(f"Wait failed: {e}")
            return {'success': False, 'error': str(e)}

    def select_option(self, selector: str, value: str) -> Dict:
        """
        Select an option from a dropdown.

        Args:
            selector: CSS selector for the select element
            value: Option value to select

        Returns:
            Dict with selection status
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        try:
            self.page.select_option(selector, value)
            
            return {
                'success': True,
                'selector': selector,
                'value': value,
                'status': 'selected'
            }
        except Exception as e:
            logger.error(f"Select failed: {e}")
            return {'success': False, 'error': str(e)}

    def upload_file(self, selector: str, file_path: str) -> Dict:
        """
        Upload a file.

        Args:
            selector: CSS selector for the file input
            file_path: Path to the file to upload

        Returns:
            Dict with upload status
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        if not os.path.exists(file_path):
            return {'success': False, 'error': f'File not found: {file_path}'}

        try:
            file_input = self.page.wait_for_selector(selector, timeout=10000)
            file_input.set_input_files(file_path)
            
            return {
                'success': True,
                'selector': selector,
                'file': file_path,
                'status': 'uploaded'
            }
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return {'success': False, 'error': str(e)}

    def get_page_content(self) -> Dict:
        """
        Get the full page content as structured data.

        Returns:
            Dict with page content
        """
        if not self.page:
            return {'success': False, 'error': 'Browser not initialized'}

        try:
            content = self.page.evaluate('''() => {
                return {
                    url: window.location.href,
                    title: document.title,
                    text: document.body.innerText,
                    links: Array.from(document.querySelectorAll('a[href]')).map(a => ({
                        text: a.innerText.trim(),
                        href: a.href
                    })).filter(l => l.text && l.href).slice(0, 50),
                    images: Array.from(document.querySelectorAll('img[src]')).map(img => ({
                        src: img.src,
                        alt: img.alt
                    })).filter(i => i.src).slice(0, 20)
                };
            }''')
            
            return {
                'success': True,
                'content': content
            }
        except Exception as e:
            logger.error(f"Get content failed: {e}")
            return {'success': False, 'error': str(e)}

    def close(self):
        """Close the browser session."""
        try:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            self._initialized = False
            logger.info(f"Browser session closed: {self.session_id}")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")


class BrowserManager:
    """Manages multiple browser sessions."""

    def __init__(self):
        self.sessions: Dict[str, BrowserSession] = {}

    def create_session(self, session_id: str = None, headless: bool = False,
                       persistent: bool = False) -> Dict:
        """
        Create a new browser session.

        Args:
            session_id: Optional session ID
            headless: Run browser headless
            persistent: Use persistent session (for logged-in sites)

        Returns:
            Dict with session info
        """
        sid = session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if sid in self.sessions:
            return {'success': False, 'error': f'Session {sid} already exists'}

        session = BrowserSession(sid, headless)
        
        user_data_dir = None
        if persistent:
            user_data_dir = str(SESSION_DIR / sid)
            Path(user_data_dir).mkdir(exist_ok=True)

        if session.start(user_data_dir):
            self.sessions[sid] = session
            return {
                'success': True,
                'session_id': sid,
                'user_data_dir': user_data_dir,
                'status': 'started'
            }
        else:
            return {'success': False, 'error': 'Failed to start browser'}

    def get_session(self, session_id: str) -> Optional[BrowserSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    def close_session(self, session_id: str) -> Dict:
        """Close a specific session."""
        if session_id not in self.sessions:
            return {'success': False, 'error': f'Session {session_id} not found'}

        session = self.sessions[session_id]
        session.close()
        del self.sessions[session_id]
        
        return {
            'success': True,
            'session_id': session_id,
            'status': 'closed'
        }

    def close_all(self):
        """Close all sessions."""
        for session_id in list(self.sessions.keys()):
            self.close_session(session_id)


# Global browser manager
browser_manager = BrowserManager()
default_session_id = None


class MCPServerHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for MCP JSON-RPC API."""

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
            # Session management
            "create_session": self.create_session,
            "close_session": self.close_session,
            "close_all_sessions": self.close_all_sessions,

            # Navigation
            "navigate": self.navigate,
            "go_back": self.go_back,
            "go_forward": self.go_forward,
            "refresh": self.refresh,

            # Form actions
            "fill": self.fill,
            "click": self.click,
            "select_option": self.select_option,
            "upload_file": self.upload_file,
            "submit_form": self.submit_form,

            # Content extraction
            "get_text": self.get_text,
            "get_html": self.get_html,
            "get_page_content": self.get_page_content,
            "screenshot": self.screenshot,

            # Advanced
            "execute_script": self.execute_script,
            "wait_for": self.wait_for,

            # Payment portal helpers
            "fill_payment": self.fill_payment,
            "process_payment": self.process_payment,

            # System
            "health_check": self.health_check,
            "get_version": self.get_version,
        }

        if method not in methods:
            raise Exception(f"Unknown method: {method}")

        return methods[method](params)

    def _get_session(self, params: Dict) -> Optional[BrowserSession]:
        """Get session from params or use default."""
        global default_session_id
        
        session_id = params.get('session_id') or default_session_id
        
        if not session_id:
            # Auto-create default session
            result = browser_manager.create_session(headless=False)
            if result['success']:
                default_session_id = result['session_id']
                return browser_manager.get_session(default_session_id)
            return None
        
        return browser_manager.get_session(session_id)

    # ==================== Session Methods ====================

    def create_session(self, params: Dict) -> Dict:
        """
        Create a new browser session.

        Params:
            session_id: str - Optional session ID
            headless: bool - Run headless (default False)
            persistent: bool - Use persistent session (default False)

        Returns:
            Dict with session info
        """
        if MCPServerHandler.demo_mode:
            return {
                'success': True,
                'session_id': 'demo_session',
                'demo_mode': True
            }

        return browser_manager.create_session(
            session_id=params.get('session_id'),
            headless=params.get('headless', False),
            persistent=params.get('persistent', False)
        )

    def close_session(self, params: Dict) -> Dict:
        """
        Close a browser session.

        Params:
            session_id: str - Session ID to close

        Returns:
            Dict with close status
        """
        if MCPServerHandler.demo_mode:
            return {'success': True, 'demo_mode': True}

        session_id = params.get('session_id')
        if not session_id:
            return {'success': False, 'error': 'session_id required'}

        return browser_manager.close_session(session_id)

    def close_all_sessions(self, params: Dict) -> Dict:
        """Close all browser sessions."""
        global default_session_id
        browser_manager.close_all()
        default_session_id = None
        return {'success': True, 'status': 'all_closed'}

    # ==================== Navigation Methods ====================

    def navigate(self, params: Dict) -> Dict:
        """
        Navigate to a URL.

        Params:
            url: str - URL to navigate to (required)
            session_id: str - Optional session ID
            wait_until: str - When to consider complete (default 'networkidle')
            timeout: int - Timeout in ms (default 60000)

        Returns:
            Dict with navigation status
        """
        if MCPServerHandler.demo_mode:
            return {
                'success': True,
                'url': params.get('url'),
                'demo_mode': True
            }

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        url = params.get('url')
        if not url:
            return {'success': False, 'error': 'url is required'}

        return session.navigate(
            url=url,
            wait_until=params.get('wait_until', 'networkidle'),
            timeout=params.get('timeout', 60000)
        )

    def go_back(self, params: Dict) -> Dict:
        """Navigate back in history."""
        if MCPServerHandler.demo_mode:
            return {'success': True, 'demo_mode': True}

        session = self._get_session(params)
        if not session or not session.page:
            return {'success': False, 'error': 'No session available'}

        try:
            session.page.go_back()
            return {'success': True, 'status': 'navigated_back'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def go_forward(self, params: Dict) -> Dict:
        """Navigate forward in history."""
        if MCPServerHandler.demo_mode:
            return {'success': True, 'demo_mode': True}

        session = self._get_session(params)
        if not session or not session.page:
            return {'success': False, 'error': 'No session available'}

        try:
            session.page.go_forward()
            return {'success': True, 'status': 'navigated_forward'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def refresh(self, params: Dict) -> Dict:
        """Refresh the current page."""
        if MCPServerHandler.demo_mode:
            return {'success': True, 'demo_mode': True}

        session = self._get_session(params)
        if not session or not session.page:
            return {'success': False, 'error': 'No session available'}

        try:
            session.page.reload()
            return {'success': True, 'status': 'refreshed'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ==================== Form Methods ====================

    def fill(self, params: Dict) -> Dict:
        """
        Fill a form field.

        Params:
            selector: str - CSS selector (required)
            value: str - Value to fill (required)
            session_id: str - Optional session ID

        Returns:
            Dict with fill status
        """
        if MCPServerHandler.demo_mode:
            return {'success': True, 'selector': params.get('selector'), 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        selector = params.get('selector')
        value = params.get('value')

        if not selector or not value:
            return {'success': False, 'error': 'selector and value are required'}

        return session.fill(selector, value)

    def click(self, params: Dict) -> Dict:
        """
        Click an element.

        Params:
            selector: str - CSS selector (required)
            session_id: str - Optional session ID
            timeout: int - Timeout in ms (default 10000)

        Returns:
            Dict with click status
        """
        if MCPServerHandler.demo_mode:
            return {'success': True, 'selector': params.get('selector'), 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        selector = params.get('selector')
        if not selector:
            return {'success': False, 'error': 'selector is required'}

        return session.click(selector, params.get('timeout', 10000))

    def select_option(self, params: Dict) -> Dict:
        """Select a dropdown option."""
        if MCPServerHandler.demo_mode:
            return {'success': True, 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        selector = params.get('selector')
        value = params.get('value')

        if not selector or not value:
            return {'success': False, 'error': 'selector and value are required'}

        return session.select_option(selector, value)

    def upload_file(self, params: Dict) -> Dict:
        """Upload a file."""
        if MCPServerHandler.demo_mode:
            return {'success': True, 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        selector = params.get('selector')
        file_path = params.get('file_path')

        if not selector or not file_path:
            return {'success': False, 'error': 'selector and file_path are required'}

        return session.upload_file(selector, file_path)

    def submit_form(self, params: Dict) -> Dict:
        """
        Submit a form.

        Params:
            selector: str - Form selector or submit button selector
            session_id: str - Optional session ID

        Returns:
            Dict with submit status
        """
        if MCPServerHandler.demo_mode:
            return {'success': True, 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        selector = params.get('selector', 'form')
        
        try:
            # Try to find submit button
            submit_btn = session.page.query_selector(f'{selector} button[type="submit"], {selector} input[type="submit"], button:has-text("Submit"), button:has-text("Continue"), button:has-text("Next")')
            if submit_btn:
                submit_btn.click()
                return {'success': True, 'status': 'submitted'}
            
            # Fallback: submit form directly
            session.page.evaluate(f'document.querySelector("{selector}").submit()')
            return {'success': True, 'status': 'submitted'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ==================== Content Methods ====================

    def get_text(self, params: Dict) -> Dict:
        """Get text content of an element."""
        if MCPServerHandler.demo_mode:
            return {'success': True, 'text': 'Demo text', 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        selector = params.get('selector')
        if not selector:
            return {'success': False, 'error': 'selector is required'}

        return session.get_text(selector)

    def get_html(self, params: Dict) -> Dict:
        """Get HTML content."""
        if MCPServerHandler.demo_mode:
            return {'success': True, 'html': '<html>Demo</html>', 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        return session.get_html(params.get('selector'))

    def get_page_content(self, params: Dict) -> Dict:
        """Get structured page content."""
        if MCPServerHandler.demo_mode:
            return {
                'success': True,
                'content': {
                    'url': 'https://example.com',
                    'title': 'Demo Page',
                    'text': 'Demo content'
                },
                'demo_mode': True
            }

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        return session.get_page_content()

    def screenshot(self, params: Dict) -> Dict:
        """Take a screenshot."""
        if MCPServerHandler.demo_mode:
            return {
                'success': True,
                'path': str(SCREENSHOTS_DIR / 'demo_screenshot.png'),
                'demo_mode': True
            }

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        return session.screenshot(
            path=params.get('path'),
            full_page=params.get('full_page', False)
        )

    # ==================== Advanced Methods ====================

    def execute_script(self, params: Dict) -> Dict:
        """Execute JavaScript code."""
        if MCPServerHandler.demo_mode:
            return {'success': True, 'result': None, 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        script = params.get('script')
        if not script:
            return {'success': False, 'error': 'script is required'}

        return session.execute_script(script)

    def wait_for(self, params: Dict) -> Dict:
        """Wait for an element."""
        if MCPServerHandler.demo_mode:
            return {'success': True, 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        selector = params.get('selector')
        if not selector:
            return {'success': False, 'error': 'selector is required'}

        return session.wait_for_selector(
            selector,
            timeout=params.get('timeout', 30000),
            state=params.get('state', 'visible')
        )

    # ==================== Payment Portal Helpers ====================

    def fill_payment(self, params: Dict) -> Dict:
        """
        Fill payment form fields.

        Params:
            card_number: str - Card number
            expiry: str - Expiry date (MM/YY)
            cvv: str - CVV code
            name: str - Cardholder name
            session_id: str - Optional session ID

        Returns:
            Dict with fill status
        """
        if MCPServerHandler.demo_mode:
            return {'success': True, 'status': 'demo_payment_filled', 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        try:
            # Common payment field selectors
            fields = {
                'card_number': params.get('card_number'),
                'cardNumber': params.get('card_number'),
                'expiry': params.get('expiry'),
                'expDate': params.get('expiry'),
                'cvv': params.get('cvv'),
                'cardName': params.get('name'),
                'name': params.get('name'),
            }

            results = []
            for selector, value in fields.items():
                if value:
                    try:
                        result = session.fill(f'input[name*="{selector}"], input[id*="{selector}"], input[placeholder*="{selector}"]', value)
                        results.append(result)
                    except:
                        pass

            return {
                'success': True,
                'fields_filled': len([r for r in results if r.get('success')]),
                'status': 'payment_fields_filled'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def process_payment(self, params: Dict) -> Dict:
        """
        Process payment by clicking submit.

        Params:
            submit_selector: str - Optional custom submit button selector
            session_id: str - Optional session ID

        Returns:
            Dict with payment status
        """
        if MCPServerHandler.demo_mode:
            return {'success': True, 'status': 'demo_payment_processed', 'demo_mode': True}

        session = self._get_session(params)
        if not session:
            return {'success': False, 'error': 'No session available'}

        try:
            # Find payment submit button
            selectors = [
                params.get('submit_selector'),
                'button[type="submit"]',
                'button:has-text("Pay")',
                'button:has-text("Complete Payment")',
                'button:has-text("Submit Payment")',
                'input[type="submit"][value*="Pay"]',
            ]

            for selector in selectors:
                if selector:
                    result = session.click(selector, timeout=5000)
                    if result.get('success'):
                        return {
                            'success': True,
                            'status': 'payment_submitted',
                            'selector_used': selector
                        }

            return {'success': False, 'error': 'Payment button not found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ==================== System Methods ====================

    def health_check(self, params: Dict) -> Dict:
        """Check server health."""
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'active_sessions': len(browser_manager.sessions),
            'demo_mode': MCPServerHandler.demo_mode
        }

    def get_version(self, params: Dict) -> Dict:
        """Get server version info."""
        return {
            'name': 'Browser MCP Server',
            'version': '1.0.0',
            'port': MCP_PORT,
            'description': 'JSON-RPC API for browser automation',
            'features': ['navigation', 'forms', 'screenshots', 'javascript', 'payment_portals']
        }


def run_server(host: str = MCP_HOST, port: int = MCP_PORT, demo_mode: bool = False):
    """Run the MCP server."""
    MCPServerHandler.demo_mode = demo_mode

    server = HTTPServer((host, port), MCPServerHandler)
    logger.info(f"Browser MCP Server starting at http://{host}:{port}")
    logger.info(f"Demo mode: {demo_mode}")
    logger.info(f"Logs: {LOG_FILE}")
    logger.info(f"Screenshots: {SCREENSHOTS_DIR}")
    logger.info("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        browser_manager.close_all()
        server.shutdown()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Browser MCP Server')
    parser.add_argument('--host', default=MCP_HOST, help=f'Host to bind to (default: {MCP_HOST})')
    parser.add_argument('--port', type=int, default=MCP_PORT, help=f'Port to bind to (default: {MCP_PORT})')
    parser.add_argument('--demo', action='store_true', help='Run in demo mode (no real browser)')
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, demo_mode=args.demo)
