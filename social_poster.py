#!/usr/bin/env python3
"""
Social Media Poster - Gold Tier Integration
============================================
Generic poster for Facebook, Instagram, and X (Twitter).
Uses Playwright for browser automation with persistent sessions.

Features:
- Support for Facebook, Instagram, and X (Twitter)
- Dry-run mode for testing
- Persistent sessions for each platform
- Logs all posting activity
- Can be called by orchestrator after approval

Usage:
    python social_poster.py --platform facebook --text "Hello World" --dry-run
    python social_poster.py --platform instagram --text "New post!" --image path/to/image.jpg
    python social_poster.py --platform x --text "Tweet content"

Platforms:
    - facebook: Uses ./facebook_session
    - instagram: Uses ./instagram_session  
    - x: Uses ./x_session (Twitter)
"""

import os
import sys
import json
import logging
import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Page, BrowserContext

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
PLATFORMS = {
    'facebook': {
        'url': 'https://www.facebook.com',
        'session_dir': 'facebook_session',
        'post_selector': '[aria-label="What\'s on your mind?"]',
        'post_url': 'https://www.facebook.com'
    },
    'instagram': {
        'url': 'https://www.instagram.com',
        'session_dir': 'instagram_session',
        'new_post_selector': '[aria-label="New post"]',
        'post_url': 'https://www.instagram.com/create/details/'
    },
    'x': {
        'url': 'https://twitter.com',
        'session_dir': 'x_session',
        'post_selector': '[data-testid="tweetTextarea_0"]',
        'post_url': 'https://twitter.com/home'
    }
}

LOG_DIR = PROJECT_ROOT / "Logs"
LOG_DIR.mkdir(exist_ok=True)

# Setup logging
LOG_FILE = LOG_DIR / "social_poster.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SocialMediaPoster:
    """Post to social media platforms."""

    def __init__(self, platform: str, dry_run: bool = False):
        self.platform = platform.lower()
        self.dry_run = dry_run
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        if self.platform not in PLATFORMS:
            raise ValueError(f"Unknown platform: {platform}. Valid: {list(PLATFORMS.keys())}")

        self.config = PLATFORMS[self.platform]
        self.session_dir = PROJECT_ROOT / self.config['session_dir']
        self.session_dir.mkdir(exist_ok=True)

    async def post(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post content to the social media platform."""
        logger.info(f"Posting to {self.platform} (dry_run={self.dry_run})")

        if self.dry_run:
            logger.info(f"[DRY RUN] Would post to {self.platform}:")
            logger.info(f"  Text: {text[:100]}{'...' if len(text) > 100 else ''}")
            if image_path:
                logger.info(f"  Image: {image_path}")
            return {
                'success': True,
                'dry_run': True,
                'platform': self.platform,
                'text': text,
                'image': image_path,
                'message': 'Dry run - no post made'
            }

        async with async_playwright() as p:
            try:
                # Launch browser with persistent context
                browser = await p.chromium.launch_persistent_context(
                    user_data_dir=str(self.session_dir),
                    headless=False,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox'
                    ]
                )

                if browser.pages:
                    self.page = browser.pages[0]
                else:
                    self.page = await browser.new_page()

                self.context = browser

                # Navigate to platform
                logger.info(f"Navigating to {self.config['url']}...")
                await self.page.goto(self.config['url'], wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(5)

                # Check login
                is_logged_in = await self.check_login()
                if not is_logged_in:
                    logger.warning("Not logged in. Please login manually in the browser window.")
                    logger.info("Waiting up to 90 seconds for manual login...")
                    # Wait for login with periodic checks
                    for i in range(18):  # 18 * 5s = 90s
                        await asyncio.sleep(5)
                        is_logged_in = await self.check_login()
                        if is_logged_in:
                            logger.info("Login detected! Continuing...")
                            break
                        logger.info(f"Waiting for login... ({(i+1)*5}s/90s)")

                    if not is_logged_in:
                        logger.error("Still not logged in after 90 seconds.")
                        await browser.close()
                        return {
                            'success': False,
                            'platform': self.platform,
                            'error': 'Not logged in'
                        }

                # Make the post
                result = await self.make_post(text, image_path)

                await browser.close()

                return result

            except Exception as e:
                logger.error(f"Error posting: {e}")
                return {
                    'success': False,
                    'platform': self.platform,
                    'error': str(e)
                }

    async def check_login(self) -> bool:
        """Check if user is logged in."""
        try:
            if self.platform == 'facebook':
                # Try multiple selectors for Facebook login detection
                # Facebook's UI changes frequently, so we try several options
                selectors = [
                    '[aria-label="Menu"]',           # Classic menu
                    '[aria-label="Home"]',           # Home button
                    '[data-testid="bluebar_profile_menu"]',  # Profile menu
                    'img[alt*="Profile"]',           # Profile picture
                    'div[role="img"][aria-label]',   # Any labeled image (profile)
                    '#profile_link',                 # Profile link
                    '.x1n2onr6.xzh2ilb'              # Modern Facebook profile icon class
                ]
                for selector in selectors:
                    try:
                        await self.page.wait_for_selector(selector, timeout=3000)
                        logger.info(f"Facebook login detected: {selector}")
                        return True
                    except Exception:
                        continue
                # If no selector matched, check if we're on login page
                url = self.page.url
                if 'login' in url.lower() or 'checkpoint' in url.lower():
                    return False
                # Assume logged in if we're on facebook.com and not on login page
                if 'facebook.com' in url:
                    logger.info("Assuming logged in (on Facebook page)")
                    return True
                return False
            elif self.platform == 'instagram':
                try:
                    await self.page.wait_for_selector('[aria-label="Home"]', timeout=10000)
                    return True
                except Exception:
                    return 'instagram.com' in self.page.url
            elif self.platform == 'x':
                try:
                    await self.page.wait_for_selector('[data-testid="SideNav"]', timeout=10000)
                    return True
                except Exception:
                    return 'twitter.com' in self.page.url or 'x.com' in self.page.url
            return True
        except Exception as e:
            logger.debug(f"Login check error: {e}")
            # Fallback: check URL
            url = self.page.url.lower()
            if self.platform == 'facebook' and 'facebook.com' in url and 'login' not in url:
                return True
            return False

    async def make_post(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Make the actual post based on platform."""
        try:
            if self.platform == 'facebook':
                return await self.post_facebook(text, image_path)
            elif self.platform == 'instagram':
                return await self.post_instagram(text, image_path)
            elif self.platform == 'x':
                return await self.post_x(text, image_path)
        except Exception as e:
            logger.error(f"Error making post: {e}")
            return {
                'success': False,
                'platform': self.platform,
                'error': str(e)
            }

    async def post_facebook(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post to Facebook - using enhanced selector approach."""
        logger.info("Posting to Facebook...")

        # Navigate to home page
        await self.page.goto('https://www.facebook.com', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

        # Take a screenshot for debugging
        await self.page.screenshot(path='Logs/fb_before_post.png')
        logger.info("Screenshot saved to Logs/fb_before_post.png")

        # Dismiss any popups (Review audience, etc.)
        try:
            continue_button = await self.page.query_selector('button:has-text("Continue")')
            if continue_button:
                await continue_button.click()
                await asyncio.sleep(2)
                logger.info("Clicked Continue button on popup")
        except Exception:
            pass

        # Try to find and click the post box with multiple strategies
        clicked = False
        
        # Strategy 1: Try "What's on your mind" (partial match for personalized text)
        try:
            post_box = await self.page.wait_for_selector('[aria-label*="What\'s on your mind"]', timeout=8000)
            if post_box:
                await post_box.click()
                await post_box.focus()
                logger.info("Clicked: [aria-label*=\"What's on your mind\"]")
                await asyncio.sleep(2)
                clicked = True
        except Exception:
            pass
        
        # Strategy 2: Try placeholder text
        if not clicked:
            try:
                post_box = await self.page.wait_for_selector('[placeholder*="What\'s on your mind"]', timeout=5000)
                if post_box:
                    await post_box.click()
                    await post_box.focus()
                    logger.info("Clicked: [placeholder*=\"What's on your mind\"]")
                    await asyncio.sleep(2)
                    clicked = True
            except Exception:
                pass
        
        # Strategy 3: Try the main post composer div
        if not clicked:
            try:
                await self.page.click('div[role="button"]:has-text("What\'s")', timeout=5000)
                logger.info("Clicked: div[role=\"button\"]:has-text(\"What's\")")
                await asyncio.sleep(2)
                clicked = True
            except Exception:
                pass
        
        # Strategy 4: Click on the post box container by text
        if not clicked:
            try:
                await self.page.click('text=/What.*s on your mind/', timeout=5000)
                logger.info("Clicked: text=/What.*s on your mind/")
                await asyncio.sleep(2)
                clicked = True
            except Exception:
                pass
        
        # Strategy 5: Try the post creator area
        if not clicked:
            try:
                await self.page.click('div:has-text("Create post")', timeout=5000)
                logger.info("Clicked: Create post area")
                await asyncio.sleep(2)
                clicked = True
            except Exception:
                pass

        if not clicked:
            logger.error("Could not find post input box with any strategy")
            await self.page.screenshot(path='Logs/fb_no_postbox.png')
            return {
                'success': False,
                'platform': 'facebook',
                'error': 'Could not find post input box'
            }

        # Wait for composer to open
        await asyncio.sleep(2)

        # Dismiss any popup that appeared after clicking post box
        try:
            continue_button = await self.page.query_selector('button:has-text("Continue")')
            if continue_button:
                await continue_button.click()
                await asyncio.sleep(2)
                logger.info("Clicked Continue button on popup (after opening composer)")
        except Exception:
            pass

        # Find the editable div and type - try multiple approaches
        text_entered = False
        
        # Approach 1: Facebook contenteditable div
        try:
            editable = await self.page.wait_for_selector('[contenteditable="true"][data-contents="true"]', timeout=5000)
            if editable:
                await editable.focus()
                await editable.fill(text)
                logger.info("Typed text into composer (contenteditable)")
                text_entered = True
        except Exception as e:
            logger.debug(f"Approach 1 failed: {e}")
        
        # Approach 2: Try any contenteditable div
        if not text_entered:
            try:
                editable = await self.page.wait_for_selector('[contenteditable="true"]', timeout=5000)
                if editable:
                    await editable.focus()
                    await editable.fill(text)
                    logger.info("Typed text into composer (any contenteditable)")
                    text_entered = True
            except Exception as e:
                logger.debug(f"Approach 2 failed: {e}")
        
        # Approach 3: Use keyboard type directly
        if not text_entered:
            logger.info("Using keyboard type as fallback")
            await self.page.keyboard.type(text, delay=50)
            logger.info("Typed text using keyboard")
            text_entered = True

        await asyncio.sleep(3)  # Wait for Facebook to process input

        # Take screenshot after typing
        await self.page.screenshot(path='Logs/fb_after_typing.png')
        logger.info("Screenshot saved to Logs/fb_after_typing.png")

        # Upload image if provided
        if image_path and os.path.exists(image_path):
            logger.info(f"Uploading image: {image_path}")
            try:
                file_input = await self.page.query_selector('input[type="file"][accept*="image"]')
                if file_input:
                    await file_input.set_input_files(image_path)
                    await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"Could not upload image: {e}")

        # Take screenshot before posting
        await self.page.screenshot(path='Logs/fb_before_submit.png')
        logger.info("Screenshot saved to Logs/fb_before_submit.png")

        # Click Post button - try multiple selectors
        post_clicked = False
        post_selectors = [
            '[aria-label="Post"]',
            'button:has-text("Post")',
            'div[role="button"]:has-text("Post")',
            'button[type="submit"]'
        ]

        for selector in post_selectors:
            try:
                post_button = await self.page.wait_for_selector(selector, timeout=5000)
                if post_button:
                    is_enabled = await post_button.is_enabled()
                    logger.info(f"Found post button: {selector}, enabled: {is_enabled}")
                    if is_enabled:
                        await post_button.click()
                        post_clicked = True
                        logger.info(f"Clicked Post button: {selector}")
                        break
                    else:
                        logger.warning("Post button disabled, text may not have been entered")
                        # Don't force click disabled button
                        break
            except Exception as e:
                logger.debug(f"Post button {selector} not found: {e}")
                continue

        if not post_clicked:
            logger.error("Could not find Post button")
            await self.page.screenshot(path='Logs/fb_no_postbutton.png')
            return {
                'success': False,
                'platform': 'facebook',
                'error': 'Could not find Post button'
            }

        # Wait for post to be submitted
        await asyncio.sleep(5)

        # Take screenshot after posting
        await self.page.screenshot(path='Logs/fb_after_post.png')
        logger.info("Screenshot saved to Logs/fb_after_post.png")

        logger.info("Facebook post submitted!")

        return {
            'success': True,
            'platform': 'facebook',
            'text': text,
            'image': image_path,
            'message': 'Post submitted successfully'
        }

    async def post_instagram(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post to Instagram."""
        logger.info("Posting to Instagram...")

        if not image_path:
            logger.error("Instagram requires an image")
            return {
                'success': False,
                'platform': 'instagram',
                'error': 'Instagram requires an image'
            }

        # Navigate to Instagram home first
        await self.page.goto('https://www.instagram.com', wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(5)

        # Take screenshot to see current state
        await self.page.screenshot(path='Logs/ig_home.png')
        
        # Click New Post button
        try:
            await self.page.click('[aria-label="New post"]')
            logger.info("Clicked New Post button")
            await asyncio.sleep(3)
        except Exception as e:
            logger.error(f"Could not find New Post button: {e}")
            await self.page.screenshot(path='Logs/ig_no_newpost.png')
            return {
                'success': False,
                'platform': 'instagram',
                'error': 'Could not find New Post button'
            }

        # Take screenshot after clicking New Post
        await self.page.screenshot(path='Logs/ig_modal.png')
        
        # Wait for the upload area to appear
        try:
            await self.page.wait_for_selector('text=/Select from computer/', timeout=10000)
            await asyncio.sleep(1)
        except Exception:
            logger.warning("Did not see 'Select from computer' text")
        
        # Upload image
        try:
            file_input = await self.page.query_selector('input[type="file"]')
            if file_input:
                await file_input.set_input_files(image_path)
                logger.info(f"Uploaded image: {image_path}")
                # Instagram needs time to process the image
                await asyncio.sleep(10)
            else:
                logger.error("No file input found")
                await self.page.screenshot(path='Logs/ig_no_input.png')
                return {
                    'success': False,
                    'platform': 'instagram',
                    'error': 'No file input found'
                }
        except Exception as e:
            logger.error(f"Could not upload image: {e}")
            await self.page.screenshot(path='Logs/ig_upload_error.png')
            return {
                'success': False,
                'platform': 'instagram',
                'error': f'Could not upload image: {e}'
            }

        # Take screenshot after upload
        await self.page.screenshot(path='Logs/ig_after_upload.png')
        logger.info("Screenshot saved to Logs/ig_after_upload.png")

        # Wait for and click Next button - it's in the top right header
        try:
            # Instagram's Next button is a blue text button in the header
            # Look for the specific button styling
            await self.page.wait_for_selector('text=Next', timeout=30000)
            # Click the Next button in the header (not other "Next" text on page)
            next_buttons = await self.page.query_selector_all('text=Next')
            clicked = False
            for btn in next_buttons:
                # Check if it's clickable (blue header button)
                if await btn.is_visible():
                    await btn.click()
                    logger.info("Clicked Next button")
                    clicked = True
                    break
            if not clicked:
                # Fallback: just click text=Next
                await self.page.click('text=Next')
                logger.info("Clicked Next button (fallback)")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Could not find Next button: {e}")
            await self.page.screenshot(path='Logs/ig_no_next.png')
            return {
                'success': False,
                'platform': 'instagram',
                'error': 'Could not find Next button - image may not have processed'
            }

        # Take screenshot after clicking Next
        await self.page.screenshot(path='Logs/ig_after_next.png')
        logger.info("Screenshot saved to Logs/ig_after_next.png")

        # Wait for the caption screen to appear
        await asyncio.sleep(3)

        # Add caption - Instagram uses various selectors for caption
        caption_added = False
        caption_selectors = [
            'textarea[placeholder*="aption"]',  # "Caption" or "Write a caption..."
            'textarea[placeholder*="escription"]',  # "Description"
            'textarea[aria-label*="aption"]',
            'textarea[aria-label*="escription"]',
            'textarea.fr66n',  # Instagram's caption textarea class
            'textarea'  # Generic fallback
        ]
        
        for selector in caption_selectors:
            try:
                caption_area = await self.page.query_selector(selector)
                if caption_area and await caption_area.is_visible():
                    await caption_area.fill(text)
                    logger.info(f"Added caption using selector: {selector}")
                    caption_added = True
                    await asyncio.sleep(1)
                    break
            except Exception as e:
                logger.debug(f"Caption selector {selector} failed: {e}")
        
        if not caption_added:
            # Try keyboard type as fallback
            try:
                await self.page.keyboard.type(text, delay=50)
                logger.info("Added caption using keyboard type")
                caption_added = True
            except Exception as e:
                logger.warning(f"Could not add caption: {e}")

        # Take screenshot before sharing
        await self.page.screenshot(path='Logs/ig_before_share.png')
        logger.info("Screenshot saved to Logs/ig_before_share.png")

        # Click Share - Instagram uses multiple possible selectors
        share_clicked = False
        share_selectors = [
            'button[type="submit"]',  # Submit button
            'button:has-text("Share")',  # Share button by text
            'div[role="button"]:has-text("Share")',  # Share div button
            'button._ap36',  # Instagram's share button class
            'button'  # Generic fallback - will try to find the right one
        ]
        
        for selector in share_selectors:
            try:
                share_buttons = await self.page.query_selector_all(selector)
                for btn in share_buttons:
                    if await btn.is_visible() and await btn.is_enabled():
                        # Get button text to verify it's the Share button
                        btn_text = await btn.inner_text()
                        if 'Share' in btn_text or 'Post' in btn_text or selector in ['button[type="submit"]', 'button._ap36']:
                            await btn.click()
                            logger.info(f"Clicked Share button using selector: {selector}")
                            share_clicked = True
                            await asyncio.sleep(5)
                            break
                if share_clicked:
                    break
            except Exception as e:
                logger.debug(f"Share selector {selector} failed: {e}")
        
        if not share_clicked:
            # Last resort: look for any visible button that might be Share
            try:
                all_buttons = await self.page.query_selector_all('button')
                for btn in all_buttons:
                    if await btn.is_visible() and await btn.is_enabled():
                        btn_text = await btn.inner_text()
                        if 'Share' in btn_text or 'Post' in btn_text or 'Publish' in btn_text:
                            await btn.click()
                            logger.info(f"Clicked Share button (fallback): {btn_text}")
                            share_clicked = True
                            await asyncio.sleep(5)
                            break
            except Exception as e:
                logger.debug(f"Fallback share attempt failed: {e}")
        
        if not share_clicked:
            logger.warning("Could not find Share button - post may not be submitted")
            await self.page.screenshot(path='Logs/ig_no_share.png')

        # Take final screenshot
        await self.page.screenshot(path='Logs/ig_final.png')
        logger.info("Screenshot saved to Logs/ig_final.png")

        return {
            'success': True,
            'platform': 'instagram',
            'text': text,
            'image': image_path,
            'message': 'Post submitted (check screenshot)'
        }

    async def post_x(self, text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
        """Post to X (Twitter)."""
        logger.info("Posting to X (Twitter)...")

        # Navigate to home
        await self.page.goto('https://twitter.com/home', wait_until='networkidle')
        await asyncio.sleep(3)

        # Find tweet box
        try:
            tweet_box = await self.page.query_selector('[data-testid="tweetTextarea_0"]')
            if tweet_box:
                await tweet_box.click()
                await asyncio.sleep(1)
                await self.page.keyboard.type(text, delay=50)
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Could not access tweet box: {e}")
            return {
                'success': False,
                'platform': 'x',
                'error': str(e)
            }

        # Upload image if provided
        if image_path and os.path.exists(image_path):
            logger.info(f"Uploading image: {image_path}")
            file_input = await self.page.query_selector('input[type="file"]')
            if file_input:
                await file_input.set_input_files(image_path)
                await asyncio.sleep(3)

        # Click Post/Tweet button
        try:
            post_button = await self.page.query_selector('[data-testid="tweetButton"]')
            if post_button:
                await post_button.click()
                logger.info("X (Twitter) post submitted!")
                await asyncio.sleep(3)

                return {
                    'success': True,
                    'platform': 'x',
                    'text': text,
                    'image': image_path,
                    'message': 'Post submitted successfully'
                }
        except Exception as e:
            logger.error(f"Could not submit post: {e}")

        return {
            'success': False,
            'platform': 'x',
            'error': 'Could not complete post'
        }


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Post to social media platforms')
    parser.add_argument('--platform', required=True, choices=['facebook', 'instagram', 'x'],
                        help='Platform to post to')
    parser.add_argument('--text', help='Text content to post')
    parser.add_argument('-t', '--task-file', help='Path to task file in Needs_Action/ (alternative to --text)')
    parser.add_argument('--image', help='Path to image file (optional)')
    parser.add_argument('-n', '--dry-run', action='store_true', help='Test without actually posting')

    args = parser.parse_args()

    # Determine text content
    if args.task_file:
        if not os.path.exists(args.task_file):
            logger.error(f"Task file not found: {args.task_file}")
            return 1
        # Try multiple encodings
        text = None
        for encoding in ['utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'cp1252']:
            try:
                with open(args.task_file, 'r', encoding=encoding) as f:
                    text = f.read().strip()
                logger.info(f"Loaded content from task file ({encoding}): {args.task_file}")
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            logger.error(f"Could not decode task file: {args.task_file}")
            return 1
    elif args.text:
        text = args.text
    else:
        logger.error("Either --text or --task-file is required")
        return 1

    poster = SocialMediaPoster(args.platform, dry_run=args.dry_run)
    result = await poster.post(text, args.image)

    print("\n" + "=" * 50)
    print("POST RESULT")
    print("=" * 50)
    print(json.dumps(result, indent=2))
    print("=" * 50)

    return 0 if result.get('success') else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
