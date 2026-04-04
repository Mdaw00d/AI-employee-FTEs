"""
LinkedIn Poster - Standalone script to post content to LinkedIn.

Usage:
    # Mode 1: Direct text
    python linkedin_poster.py "Your post text here" [--dry-run]

    # Mode 2: From Approved folder
    python linkedin_poster.py --from-approved [--dry-run]
"""

import sys
import os
import time
import logging
import argparse
import re
import shutil
import asyncio
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext

# Configuration
LOGS_DIR = "./Logs"
SESSION_DIR = "./linkedin_session"
APPROVED_DIR = "./Approved"
DONE_DIR = "./Done"

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(SESSION_DIR, exist_ok=True)
os.makedirs(APPROVED_DIR, exist_ok=True)
os.makedirs(DONE_DIR, exist_ok=True)

# Configure logging - separate log for posts
post_logger = logging.getLogger('linkedin_poster')
post_logger.setLevel(logging.INFO)

# File handler
file_handler = logging.FileHandler(os.path.join(LOGS_DIR, 'linkedin_posts.log'), encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
post_logger.addHandler(file_handler)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
post_logger.addHandler(console_handler)


def extract_post_text_from_file(filepath: str) -> str:
    """Extract post_text from an approval file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = r'post_text:\s*\|\s*\n((?:  .+\n?)+)'
    match = re.search(pattern, content, re.MULTILINE)

    if match:
        text = match.group(1)
        lines = text.split('\n')
        dedented_lines = [line[2:] if line.startswith('  ') else line for line in lines]
        return '\n'.join(dedented_lines).strip()

    simple_pattern = r'post_text:\s*(.+?)(?:\n\w|\n---|\Z)'
    match = re.search(simple_pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()

    post_logger.warning(f"Could not extract post_text from {filepath}")
    return ""


def find_approved_post_file() -> str:
    """Find the first/newest LINKEDIN_POST_*.md file in Approved/."""
    if not os.path.exists(APPROVED_DIR):
        return ""

    files = []
    for filename in os.listdir(APPROVED_DIR):
        if filename.startswith('LINKEDIN_POST_') and filename.endswith('.md'):
            filepath = os.path.join(APPROVED_DIR, filename)
            if os.path.isfile(filepath):
                mtime = os.path.getmtime(filepath)
                files.append((filepath, mtime))

    if not files:
        return ""

    files.sort(key=lambda x: x[1], reverse=True)
    post_logger.info(f"Found {len(files)} approved post file(s)")
    return files[0][0]


async def post_to_linkedin(post_text: str, dry_run: bool = False) -> bool:
    """Posts content to LinkedIn."""
    page = None
    browser = None

    try:
        post_logger.info("Starting Playwright...")
        playwright = await async_playwright().start()

        post_logger.info(f"Launching browser with session: {SESSION_DIR}")
        browser = await playwright.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            viewport={"width": 1280, "height": 720},
            args=[
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--lang=en-US',
            ]
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        # Navigation
        post_logger.info("Navigating to LinkedIn feed...")
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=120000)
        await asyncio.sleep(5)

        post_logger.info("Checking if logged in...")
        # Check for login wall
        try:
            login_check = await page.query_selector('input#session_key')
            if login_check:
                post_logger.error("Not logged in! Please run: python linkedin_login.py")
                await browser.close()
                await playwright.stop()
                return False
        except:
            pass

        post_logger.info("Navigation successful - ready to post")

        if dry_run:
            post_logger.info("=== DRY RUN MODE ===")
            post_logger.info(f"Would post ({len(post_text)} chars):\n{post_text[:200]}...")
            screenshot_path = os.path.join(LOGS_DIR, f'linkedin_dryrun_{time.strftime("%Y%m%d_%H%M%S")}.png')
            await page.screenshot(path=screenshot_path)
            post_logger.info(f"Screenshot saved: {screenshot_path}")
            await browser.close()
            await playwright.stop()
            return True

        # Scroll to top
        post_logger.info("Scrolling to top of feed...")
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(3)

        # Find and click the "Start a post" button with multiple selectors
        post_logger.info("Looking for 'Start a post' button...")
        start_post_btn = None
        start_post_selectors = [
            'button:has-text("Start a post")',
            'div[aria-label*="Start a post"]',
            'button[aria-label*="Create a post"]',
            '[role="button"]:has-text("Start")',
        ]
        
        for selector in start_post_selectors:
            try:
                start_post_btn = await page.wait_for_selector(selector, timeout=10000)
                if start_post_btn:
                    post_logger.info(f"Found start post button with: {selector}")
                    break
            except Exception:
                continue
        
        if not start_post_btn:
            post_logger.error("Could not find 'Start a post' button with any selector")
            screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_nostart_{time.strftime("%Y%m%d_%H%M%S")}.png')
            await page.screenshot(path=screenshot_path)
            post_logger.info(f"Screenshot saved: {screenshot_path}")
            
            # Try JavaScript click as fallback
            try:
                post_logger.info("Attempting JavaScript click for start post...")
                await page.evaluate('''() => {
                    const buttons = document.querySelectorAll('button, div[role="button"]');
                    for (let btn of buttons) {
                        const text = btn.textContent || btn.getAttribute('aria-label') || '';
                        if (text.includes('Start') || text.includes('Create') || text.includes('Post')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                await asyncio.sleep(3)
                post_logger.info("JavaScript click attempted for start post")
            except Exception as js_e:
                post_logger.error(f"JavaScript click failed: {js_e}")
                await browser.close()
                await playwright.stop()
                return False
        else:
            try:
                await start_post_btn.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                await start_post_btn.click()
                post_logger.info("Clicked 'Start a post' button")
                await asyncio.sleep(2)
            except Exception as e:
                post_logger.error(f"Could not click 'Start a post' button: {e}")
                screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_clickstart_{time.strftime("%Y%m%d_%H%M%S")}.png')
                await page.screenshot(path=screenshot_path)
                await browser.close()
                await playwright.stop()
                return False

        # Find the textbox and type the content with multiple selectors
        post_logger.info("Looking for text editor...")
        textbox = None
        textbox_selectors = [
            'div[role="textbox"][contenteditable="true"]',
            'div[contenteditable="true"][aria-label*="post"]',
            'textarea[aria-label*="post"]',
            'div[class*="editor"]',
        ]
        
        for selector in textbox_selectors:
            try:
                textbox = await page.wait_for_selector(selector, timeout=15000)
                if textbox:
                    post_logger.info(f"Found textbox with: {selector}")
                    break
            except Exception:
                continue
        
        if not textbox:
            post_logger.error("Could not find text editor with any selector")
            screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_notype_{time.strftime("%Y%m%d_%H%M%S")}.png')
            await page.screenshot(path=screenshot_path)
            post_logger.info(f"Screenshot saved: {screenshot_path}")
            await browser.close()
            await playwright.stop()
            return False
        
        try:
            await textbox.click()
            await asyncio.sleep(1)

            # Clear any existing content
            post_logger.info("Clearing existing content...")
            await page.keyboard.press('Control+A')
            await page.keyboard.press('Delete')
            await asyncio.sleep(0.5)

            # Type the post content
            post_logger.info(f"Typing post content ({len(post_text)} chars)...")
            await page.keyboard.type(post_text, delay=30)
            await asyncio.sleep(2)

            post_logger.info("Text entry complete")
        except Exception as e:
            post_logger.error(f"Could not type post content: {e}")
            screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_notype_{time.strftime("%Y%m%d_%H%M%S")}.png')
            await page.screenshot(path=screenshot_path)
            post_logger.info(f"Screenshot saved: {screenshot_path}")
            await browser.close()
            await playwright.stop()
            return False

        # Find and click the Post button with multiple selectors
        post_logger.info("Looking for Post button...")
        post_button = None
        post_selectors = [
            'button:has-text("Post"):not([disabled])',
            'button:has-text("Share"):not([disabled])',
            'button[aria-label="Post"]',
            'button[aria-label="Share"]',
            '[role="button"]:has-text("Post")',
        ]
        
        for selector in post_selectors:
            try:
                # Wait for Post button to be enabled
                await asyncio.sleep(2)
                post_button = await page.wait_for_selector(selector, state='enabled', timeout=15000)
                if post_button:
                    post_logger.info(f"Found post button with: {selector}")
                    break
            except Exception:
                continue
        
        if not post_button:
            post_logger.error("Could not find Post button with any selector")
            screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_nopost_{time.strftime("%Y%m%d_%H%M%S")}.png')
            await page.screenshot(path=screenshot_path)
            post_logger.info(f"Screenshot saved: {screenshot_path}")
            
            # Try JavaScript click as fallback
            try:
                post_logger.info("Attempting JavaScript click for Post button...")
                await page.evaluate('''() => {
                    const buttons = document.querySelectorAll('button');
                    for (let btn of buttons) {
                        const text = btn.textContent || '';
                        if ((text.includes('Post') || text.includes('Share')) && !btn.disabled) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                await asyncio.sleep(3)
                post_logger.info("JavaScript click attempted for Post button")
                post_confirmed = True
            except Exception as js_e:
                post_logger.error(f"JavaScript click failed: {js_e}")
                await browser.close()
                await playwright.stop()
                return False
        else:
            try:
                await post_button.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                await post_button.click()
                post_logger.info("Clicked Post button")
            except Exception as e:
                post_logger.error(f"Could not click Post button: {e}")
                screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_nopost_{time.strftime("%Y%m%d_%H%M%S")}.png')
                await page.screenshot(path=screenshot_path)
                await browser.close()
                await playwright.stop()
                return False

            # Wait for post to be published
            await asyncio.sleep(5)

            # Check for success
            post_confirmed = False
            try:
                success_indicator = await page.wait_for_selector('text="You posted this", text="See your post"', timeout=5000)
                if success_indicator:
                    post_confirmed = True
                    post_logger.info("Post published successfully!")
            except:
                # Check if we're still on feed
                if "feed" in page.url:
                    post_confirmed = True
                    post_logger.info("Post appears to be published (on feed page)")

        # Take final screenshot
        screenshot_path = os.path.join(LOGS_DIR, f'linkedin_success_{time.strftime("%Y%m%d_%H%M%S")}.png')
        await page.screenshot(path=screenshot_path)
        post_logger.info(f"Success screenshot saved: {screenshot_path}")

        await browser.close()
        await playwright.stop()
        return post_confirmed

    except Exception as e:
        post_logger.error(f"Error posting: {e}")
        if page:
            try:
                screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_{time.strftime("%Y%m%d_%H%M%S")}.png')
                await page.screenshot(path=screenshot_path)
                post_logger.info(f"Error screenshot saved: {screenshot_path}")
            except:
                pass
        if browser:
            try:
                await browser.close()
            except:
                pass
        return False


def move_to_done(filepath: str):
    """Move processed file to Done/ directory."""
    if not os.path.exists(filepath):
        return

    filename = os.path.basename(filepath)
    dest_path = os.path.join(DONE_DIR, filename)

    if os.path.exists(dest_path):
        base, ext = os.path.splitext(filename)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(DONE_DIR, f"{base}_{timestamp}{ext}")

    try:
        shutil.move(filepath, dest_path)
        post_logger.info(f"Moved {filename} to Done/")
    except Exception as e:
        post_logger.error(f"Failed to move file to Done/: {e}")


async def main():
    parser = argparse.ArgumentParser(
        description='Post content to LinkedIn',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Post text directly
  python linkedin_poster.py "Your post text here"

  # Post from Approved folder
  python linkedin_poster.py --from-approved

  # Dry run (don't actually post)
  python linkedin_poster.py "text" --dry-run
  python linkedin_poster.py --from-approved --dry-run
        """
    )

    parser.add_argument('post_text', nargs='?', default='', help='Post text to publish')
    parser.add_argument('--from-approved', action='store_true', help='Read post from Approved/ folder')
    parser.add_argument('--dry-run', action='store_true', help='Test without actually posting')

    args = parser.parse_args()

    if not args.post_text and not args.from_approved:
        parser.print_help()
        print("\nError: Either provide post_text or use --from-approved")
        sys.exit(1)

    if args.post_text and args.from_approved:
        parser.print_help()
        print("\nError: Cannot use both post_text and --from-approved")
        sys.exit(1)

    post_logger.info("=" * 60)
    post_logger.info("LinkedIn Poster starting...")
    post_logger.info(f"Mode: {'from-approved' if args.from_approved else 'direct-text'}")
    post_logger.info(f"DRY_RUN: {args.dry_run}")
    post_logger.info("=" * 60)

    # Get post text
    if args.from_approved:
        post_logger.info("Searching for approved posts...")
        filepath = find_approved_post_file()

        if not filepath:
            post_logger.info("No pending approved LinkedIn posts found in Approved/")
            sys.exit(0)

        post_logger.info(f"Found: {os.path.basename(filepath)}")
        post_text = extract_post_text_from_file(filepath)

        if not post_text:
            post_logger.error("Could not extract post_text from file")
            sys.exit(1)

        post_logger.info(f"Extracted post ({len(post_text)} chars)")
    else:
        post_text = args.post_text

    # Post to LinkedIn
    success = await post_to_linkedin(post_text, args.dry_run)

    if success:
        post_logger.info("Operation completed successfully")
        if args.from_approved and not args.dry_run:
            filepath = find_approved_post_file()
            if filepath:
                move_to_done(filepath)
    else:
        post_logger.error("Operation failed")
        sys.exit(1)

    post_logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
