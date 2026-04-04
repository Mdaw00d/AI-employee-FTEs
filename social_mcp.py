#!/usr/bin/env python3
"""
Social Media MCP Server - JSON-RPC API for Social Media Posting
================================================================
Provides a local MCP server for posting to LinkedIn, Facebook, Instagram, and X (Twitter).
Uses Playwright for browser automation.

Features:
- Post to LinkedIn
- Post to Facebook
- Post to Instagram
- Post to X (Twitter)
- Schedule posts
- Get post status

Usage:
    python social_mcp.py

Server runs at: http://localhost:8001
Logs written to: Logs/social_mcp.log

Integration with Orchestrator:
    When social post needed, orchestrator calls:
    POST http://localhost:8001/rpc
    with method: post_linkedin, post_facebook, post_instagram, post_x

Session Management:
    Sessions stored in ./social_sessions/ directory
    First run: Login manually in browser
    Subsequent runs: Session reused
"""

import os
import sys
import io
import json
import logging
import time
import subprocess
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# MCP Server Configuration
MCP_HOST = "localhost"
MCP_PORT = 8001  # Social Media MCP port

# Logging
LOG_DIR = Path("Logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "social_mcp.log"

# Session directories
SESSION_DIR = Path("social_sessions")
SESSION_DIR.mkdir(exist_ok=True)

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


class SocialMediaPoster:
    """Handles posting to various social media platforms via Playwright."""

    def __init__(self, session_dir: str = None):
        self.session_dir = session_dir or str(SESSION_DIR)
        self._executor = ThreadPoolExecutor(max_workers=3)

    def post_to_linkedin(self, text: str, image_path: str = None, 
                         dry_run: bool = False) -> Dict:
        """
        Post to LinkedIn using the existing linkedin_poster.py script.

        Args:
            text: Post content
            image_path: Optional path to image
            dry_run: If True, don't actually post

        Returns:
            Dict with post status
        """
        logger.info(f"Posting to LinkedIn (dry_run={dry_run})")

        if dry_run:
            return {
                'success': True,
                'platform': 'linkedin',
                'status': 'dry_run',
                'text_preview': text[:100] + '...' if len(text) > 100 else text,
                'demo_mode': True
            }

        try:
            # Call the existing linkedin_poster.py script
            script_path = Path(__file__).parent / "linkedin_poster.py"
            
            if not script_path.exists():
                logger.error("linkedin_poster.py not found")
                return {
                    'success': False,
                    'platform': 'linkedin',
                    'error': 'linkedin_poster.py script not found'
                }

            # Run the script with the post text
            cmd = [sys.executable, str(script_path), text]
            if dry_run:
                cmd.append("--dry-run")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(Path(__file__).parent)
            )

            if result.returncode == 0:
                logger.info("LinkedIn post successful")
                return {
                    'success': True,
                    'platform': 'linkedin',
                    'status': 'posted',
                    'text_preview': text[:100] + '...' if len(text) > 100 else text,
                    'timestamp': datetime.now().isoformat()
                }
            else:
                logger.error(f"LinkedIn post failed: {result.stderr}")
                return {
                    'success': False,
                    'platform': 'linkedin',
                    'error': result.stderr[:500] if result.stderr else 'Unknown error'
                }

        except subprocess.TimeoutExpired:
            logger.error("LinkedIn post timed out")
            return {
                'success': False,
                'platform': 'linkedin',
                'error': 'Post operation timed out (180s)'
            }
        except Exception as e:
            logger.error(f"Error posting to LinkedIn: {e}")
            return {
                'success': False,
                'platform': 'linkedin',
                'error': str(e)
            }

    def post_to_facebook(self, text: str, image_path: str = None,
                         dry_run: bool = False) -> Dict:
        """
        Post to Facebook using Playwright.

        Args:
            text: Post content
            image_path: Optional path to image
            dry_run: If True, don't actually post

        Returns:
            Dict with post status
        """
        logger.info(f"Posting to Facebook (dry_run={dry_run})")

        if dry_run:
            return {
                'success': True,
                'platform': 'facebook',
                'status': 'dry_run',
                'text_preview': text[:100] + '...' if len(text) > 100 else text,
                'demo_mode': True
            }

        try:
            # Call the existing facebook_watcher.py infrastructure
            # For now, use Playwright directly
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            browser = None
            page = None

            try:
                browser = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(SESSION_DIR / "facebook"),
                    headless=False,
                    viewport={"width": 1280, "height": 720},
                    args=['--disable-gpu', '--disable-dev-shm-usage', '--no-sandbox']
                )

                page = browser.new_page()
                logger.info("Navigating to Facebook...")
                page.goto("https://www.facebook.com", wait_until='networkidle', timeout=60000)
                time.sleep(3)

                # Check if logged in
                if not page.query_selector('[aria-label="Menu"]'):
                    logger.warning("Not logged in to Facebook. Please login manually.")
                    time.sleep(30)  # Wait for manual login

                # Find and click the "What's on your mind?" box
                logger.info("Looking for post composer...")
                composer_selectors = [
                    '[placeholder="What\'s on your mind?"]',
                    '[placeholder="What\'s on your mind, ?"]',
                    'button:has-text("What\'s on your mind?")',
                    '[aria-label*="What\'s on your mind"]',
                ]

                composer = None
                for selector in composer_selectors:
                    try:
                        composer = page.query_selector(selector)
                        if composer:
                            logger.info(f"Found composer via: {selector}")
                            break
                    except:
                        continue

                if not composer:
                    # Fallback: navigate directly to post creation
                    logger.info("Composer not found, trying direct navigation...")
                    page.goto("https://www.facebook.com/feed/composer", wait_until='networkidle')
                    time.sleep(3)

                # Click composer to open full dialog
                if composer:
                    composer.click()
                    time.sleep(2)

                # Find the text area and type the post
                logger.info("Entering post text...")
                text_selectors = [
                    '[role="textbox"][contenteditable="true"]',
                    '[placeholder*="What\'s on your mind"]',
                    'div[contenteditable="true"]',
                ]

                text_area = None
                for selector in text_selectors:
                    try:
                        text_area = page.wait_for_selector(selector, timeout=10000)
                        if text_area:
                            logger.info(f"Found text area via: {selector}")
                            break
                    except:
                        continue

                if not text_area:
                    logger.error("Could not find text area")
                    return {
                        'success': False,
                        'platform': 'facebook',
                        'error': 'Could not find post text area'
                    }

                # Type the post content
                text_area.focus()
                time.sleep(1)
                
                # Type in chunks
                chunk_size = 50
                for i in range(0, len(text), chunk_size):
                    chunk = text[i:i+chunk_size]
                    page.keyboard.type(chunk, delay=20)
                    time.sleep(0.05)

                logger.info("Text entered successfully")

                # Upload image if provided
                if image_path and os.path.exists(image_path):
                    logger.info(f"Uploading image: {image_path}")
                    # Find and click photo/video button
                    photo_button = page.query_selector('[aria-label*="photo"], [aria-label*="image"], [aria-label*="video"]')
                    if photo_button:
                        photo_button.click()
                        time.sleep(2)
                        # Upload file
                        file_input = page.query_selector('input[type="file"]')
                        if file_input:
                            file_input.set_input_files(image_path)
                            time.sleep(3)

                # Find and click Post button
                logger.info("Looking for Post button...")
                post_selectors = [
                    'button:has-text("Post")',
                    '[aria-label="Post"]',
                    'button[data-testid*="post"]',
                ]

                post_button = None
                for selector in post_selectors:
                    try:
                        post_button = page.query_selector(selector)
                        if post_button and post_button.is_visible():
                            logger.info(f"Found Post button via: {selector}")
                            break
                    except:
                        continue

                if post_button:
                    post_button.click()
                    logger.info("Post button clicked")
                    time.sleep(5)

                    # Check for success
                    if page.url and "feed" in page.url.lower():
                        logger.info("Facebook post appears successful")
                        return {
                            'success': True,
                            'platform': 'facebook',
                            'status': 'posted',
                            'text_preview': text[:100] + '...' if len(text) > 100 else text,
                            'timestamp': datetime.now().isoformat()
                        }
                else:
                    logger.warning("Post button not found")

                return {
                    'success': True,
                    'platform': 'facebook',
                    'status': 'content_entered',
                    'note': 'Manual post submission may be required',
                    'text_preview': text[:100] + '...' if len(text) > 100 else text
                }

            finally:
                if browser:
                    browser.close()
                playwright.stop()

        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright")
            return {
                'success': False,
                'platform': 'facebook',
                'error': 'Playwright not installed'
            }
        except Exception as e:
            logger.error(f"Error posting to Facebook: {e}")
            return {
                'success': False,
                'platform': 'facebook',
                'error': str(e)[:500]
            }

    def post_to_instagram(self, text: str, image_path: str = None,
                          dry_run: bool = False) -> Dict:
        """
        Post to Instagram using Playwright.

        Args:
            text: Post caption
            image_path: Path to image (required for Instagram)
            dry_run: If True, don't actually post

        Returns:
            Dict with post status
        """
        logger.info(f"Posting to Instagram (dry_run={dry_run})")

        if not image_path:
            return {
                'success': False,
                'platform': 'instagram',
                'error': 'Image path is required for Instagram posts'
            }

        if not os.path.exists(image_path):
            return {
                'success': False,
                'platform': 'instagram',
                'error': f'Image not found: {image_path}'
            }

        if dry_run:
            return {
                'success': True,
                'platform': 'instagram',
                'status': 'dry_run',
                'caption_preview': text[:100] + '...' if len(text) > 100 else text,
                'image': image_path,
                'demo_mode': True
            }

        try:
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            browser = None
            page = None

            try:
                browser = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(SESSION_DIR / "instagram"),
                    headless=False,
                    viewport={"width": 1280, "height": 720},
                    args=['--disable-gpu', '--disable-dev-shm-usage', '--no-sandbox']
                )

                page = browser.new_page()
                logger.info("Navigating to Instagram...")
                page.goto("https://www.instagram.com", wait_until='networkidle', timeout=60000)
                time.sleep(3)

                # Check if logged in
                if not page.query_selector('[aria-label*="Profile"]'):
                    logger.warning("Not logged in to Instagram. Please login manually.")
                    time.sleep(30)

                # Click create/new post button
                logger.info("Looking for create post button...")
                create_selectors = [
                    '[aria-label*="New post"]',
                    '[aria-label*="Create"]',
                    'svg[aria-label*="new"]',
                ]

                create_button = None
                for selector in create_selectors:
                    try:
                        create_button = page.query_selector(selector)
                        if create_button:
                            break
                    except:
                        continue

                if create_button:
                    create_button.click()
                    time.sleep(2)

                # Upload image
                logger.info(f"Uploading image: {image_path}")
                file_input = page.wait_for_selector('input[type="file"]', timeout=10000)
                if file_input:
                    file_input.set_input_files(image_path)
                    time.sleep(3)

                # Click Next
                next_button = page.query_selector('button:has-text("Next")')
                if next_button:
                    next_button.click()
                    time.sleep(2)

                # Add caption
                if text:
                    logger.info("Adding caption...")
                    caption_area = page.query_selector('textarea')
                    if caption_area:
                        caption_area.fill(text)
                        time.sleep(1)

                # Click Share/Post
                share_button = page.query_selector('button:has-text("Share")')
                if share_button:
                    share_button.click()
                    logger.info("Share button clicked")
                    time.sleep(5)

                    return {
                        'success': True,
                        'platform': 'instagram',
                        'status': 'posted',
                        'caption_preview': text[:100] + '...' if len(text) > 100 else text,
                        'image': image_path,
                        'timestamp': datetime.now().isoformat()
                    }

                return {
                    'success': True,
                    'platform': 'instagram',
                    'status': 'content_entered',
                    'note': 'Manual post submission may be required'
                }

            finally:
                if browser:
                    browser.close()
                playwright.stop()

        except ImportError:
            logger.error("Playwright not installed")
            return {
                'success': False,
                'platform': 'instagram',
                'error': 'Playwright not installed'
            }
        except Exception as e:
            logger.error(f"Error posting to Instagram: {e}")
            return {
                'success': False,
                'platform': 'instagram',
                'error': str(e)[:500]
            }

    def post_to_x(self, text: str, image_path: str = None,
                  dry_run: bool = False) -> Dict:
        """
        Post to X (Twitter) using Playwright.

        Args:
            text: Tweet content (max 280 chars for standard)
            image_path: Optional path to image
            dry_run: If True, don't actually post

        Returns:
            Dict with post status
        """
        logger.info(f"Posting to X/Twitter (dry_run={dry_run})")

        if dry_run:
            return {
                'success': True,
                'platform': 'x',
                'status': 'dry_run',
                'text_preview': text[:100] + '...' if len(text) > 100 else text,
                'demo_mode': True
            }

        try:
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            browser = None
            page = None

            try:
                browser = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(SESSION_DIR / "x"),
                    headless=False,
                    viewport={"width": 1280, "height": 720},
                    args=['--disable-gpu', '--disable-dev-shm-usage', '--no-sandbox']
                )

                page = browser.new_page()
                logger.info("Navigating to X (Twitter)...")
                page.goto("https://twitter.com/home", wait_until='networkidle', timeout=60000)
                time.sleep(3)

                # Check if logged in
                if page.url and "login" in page.url.lower():
                    logger.warning("Not logged in to X. Please login manually.")
                    time.sleep(30)

                # Find the tweet composer
                logger.info("Looking for tweet composer...")
                composer_selectors = [
                    '[data-testid="tweetTextarea_0"]',
                    '[role="textbox"][data-testid="tweetTextarea_0"]',
                    '[placeholder*="What is happening"]',
                ]

                composer = None
                for selector in composer_selectors:
                    try:
                        composer = page.wait_for_selector(selector, timeout=10000)
                        if composer:
                            logger.info(f"Found composer via: {selector}")
                            break
                    except:
                        continue

                if not composer:
                    logger.error("Could not find tweet composer")
                    return {
                        'success': False,
                        'platform': 'x',
                        'error': 'Could not find tweet composer'
                    }

                # Click and type
                composer.click()
                time.sleep(1)

                # Type the tweet
                logger.info("Entering tweet text...")
                page.keyboard.type(text, delay=20)
                time.sleep(1)

                # Upload image if provided
                if image_path and os.path.exists(image_path):
                    logger.info(f"Uploading image: {image_path}")
                    # Click media button
                    media_button = page.query_selector('[data-testid*="media"], [aria-label*="media"], [aria-label*="image"]')
                    if media_button:
                        media_button.click()
                        time.sleep(2)
                        file_input = page.wait_for_selector('input[type="file"]', timeout=10000)
                        if file_input:
                            file_input.set_input_files(image_path)
                            time.sleep(3)

                # Click Post/Tweet button
                logger.info("Looking for Post button...")
                post_selectors = [
                    'button[data-testid="tweetButton"]',
                    'button[data-testid="tweetButtonInline"]',
                    'button:has-text("Post")',
                    'button:has-text("Tweet")',
                ]

                post_button = None
                for selector in post_selectors:
                    try:
                        post_button = page.query_selector(selector)
                        if post_button and post_button.is_visible():
                            logger.info(f"Found Post button via: {selector}")
                            break
                    except:
                        continue

                if post_button:
                    post_button.click()
                    logger.info("Post button clicked")
                    time.sleep(5)

                    return {
                        'success': True,
                        'platform': 'x',
                        'status': 'posted',
                        'text_preview': text[:100] + '...' if len(text) > 100 else text,
                        'timestamp': datetime.now().isoformat()
                    }

                return {
                    'success': True,
                    'platform': 'x',
                    'status': 'content_entered',
                    'note': 'Manual post submission may be required'
                }

            finally:
                if browser:
                    browser.close()
                playwright.stop()

        except ImportError:
            logger.error("Playwright not installed")
            return {
                'success': False,
                'platform': 'x',
                'error': 'Playwright not installed'
            }
        except Exception as e:
            logger.error(f"Error posting to X: {e}")
            return {
                'success': False,
                'platform': 'x',
                'error': str(e)[:500]
            }


class MCPServerHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for MCP JSON-RPC API."""

    poster: Optional[SocialMediaPoster] = None
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
            # Platform-specific posting
            "post_linkedin": self.post_linkedin,
            "post_facebook": self.post_facebook,
            "post_instagram": self.post_instagram,
            "post_x": self.post_x,
            "post_twitter": self.post_x,  # Alias

            # Generic posting
            "post": self.post,

            # System Operations
            "health_check": self.health_check,
            "get_version": self.get_version,
        }

        if method not in methods:
            raise Exception(f"Unknown method: {method}")

        return methods[method](params)

    # ==================== Social Media Methods ====================

    def post_linkedin(self, params: Dict) -> Dict:
        """
        Post to LinkedIn.

        Params:
            text: str - Post content (required)
            image_path: str - Optional path to image
            dry_run: bool - If True, don't actually post

        Returns:
            Dict with post status
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.poster:
            return {
                'success': True,
                'platform': 'linkedin',
                'status': 'demo',
                'text_preview': params.get('text', '')[:100],
                'demo_mode': True
            }

        text = params.get('text')
        if not text:
            raise Exception("text is required")

        return MCPServerHandler.poster.post_to_linkedin(
            text=text,
            image_path=params.get('image_path'),
            dry_run=params.get('dry_run', False)
        )

    def post_facebook(self, params: Dict) -> Dict:
        """
        Post to Facebook.

        Params:
            text: str - Post content (required)
            image_path: str - Optional path to image
            dry_run: bool - If True, don't actually post

        Returns:
            Dict with post status
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.poster:
            return {
                'success': True,
                'platform': 'facebook',
                'status': 'demo',
                'text_preview': params.get('text', '')[:100],
                'demo_mode': True
            }

        text = params.get('text')
        if not text:
            raise Exception("text is required")

        return MCPServerHandler.poster.post_to_facebook(
            text=text,
            image_path=params.get('image_path'),
            dry_run=params.get('dry_run', False)
        )

    def post_instagram(self, params: Dict) -> Dict:
        """
        Post to Instagram.

        Params:
            text: str - Caption content (required)
            image_path: str - Path to image (required)
            dry_run: bool - If True, don't actually post

        Returns:
            Dict with post status
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.poster:
            return {
                'success': True,
                'platform': 'instagram',
                'status': 'demo',
                'caption_preview': params.get('text', '')[:100],
                'demo_mode': True
            }

        text = params.get('text')
        image_path = params.get('image_path')

        if not text:
            raise Exception("text (caption) is required")
        if not image_path:
            raise Exception("image_path is required for Instagram")

        return MCPServerHandler.poster.post_to_instagram(
            text=text,
            image_path=image_path,
            dry_run=params.get('dry_run', False)
        )

    def post_x(self, params: Dict) -> Dict:
        """
        Post to X (Twitter).

        Params:
            text: str - Tweet content (required)
            image_path: str - Optional path to image
            dry_run: bool - If True, don't actually post

        Returns:
            Dict with post status
        """
        if MCPServerHandler.demo_mode or not MCPServerHandler.poster:
            return {
                'success': True,
                'platform': 'x',
                'status': 'demo',
                'text_preview': params.get('text', '')[:100],
                'demo_mode': True
            }

        text = params.get('text')
        if not text:
            raise Exception("text is required")

        return MCPServerHandler.poster.post_to_x(
            text=text,
            image_path=params.get('image_path'),
            dry_run=params.get('dry_run', False)
        )

    def post(self, params: Dict) -> Dict:
        """
        Post to a specified platform.

        Params:
            platform: str - Platform name (linkedin, facebook, instagram, x) (required)
            text: str - Post content (required)
            image_path: str - Optional path to image
            dry_run: bool - If True, don't actually post

        Returns:
            Dict with post status
        """
        platform = params.get('platform', '').lower()
        text = params.get('text')

        if not platform:
            raise Exception("platform is required")
        if not text:
            raise Exception("text is required")

        platform_methods = {
            'linkedin': self.post_linkedin,
            'facebook': self.post_facebook,
            'instagram': self.post_instagram,
            'x': self.post_x,
            'twitter': self.post_x,
        }

        if platform not in platform_methods:
            raise Exception(f"Unknown platform: {platform}")

        return platform_methods[platform](params)

    # ==================== System Methods ====================

    def health_check(self, params: Dict) -> Dict:
        """Check server health."""
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'demo_mode': MCPServerHandler.demo_mode
        }

    def get_version(self, params: Dict) -> Dict:
        """Get server version info."""
        return {
            'name': 'Social Media MCP Server',
            'version': '1.0.0',
            'port': MCP_PORT,
            'platforms': ['linkedin', 'facebook', 'instagram', 'x'],
            'description': 'JSON-RPC API for social media posting'
        }


def run_server(host: str = MCP_HOST, port: int = MCP_PORT, demo_mode: bool = False):
    """Run the MCP server."""
    MCPServerHandler.demo_mode = demo_mode

    if not demo_mode:
        logger.info("Initializing Social Media Poster...")
        MCPServerHandler.poster = SocialMediaPoster(str(SESSION_DIR))

    server = HTTPServer((host, port), MCPServerHandler)
    logger.info(f"Social Media MCP Server starting at http://{host}:{port}")
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

    parser = argparse.ArgumentParser(description='Social Media MCP Server')
    parser.add_argument('--host', default=MCP_HOST, help=f'Host to bind to (default: {MCP_HOST})')
    parser.add_argument('--port', type=int, default=MCP_PORT, help=f'Port to bind to (default: {MCP_PORT})')
    parser.add_argument('--demo', action='store_true', help='Run in demo mode (no real posts)')
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, demo_mode=args.demo)
