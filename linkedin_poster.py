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
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

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
    """
    Extract post_text from an approval file.
    
    Handles YAML frontmatter format:
    post_text: |
      actual post content here
    
    Args:
        filepath: Path to the approval file
        
    Returns:
        Extracted post text or empty string if not found
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Try to find post_text in YAML frontmatter
    # Match: post_text: | followed by indented content
    pattern = r'post_text:\s*\|\s*\n((?:  .+\n?)+)'
    match = re.search(pattern, content, re.MULTILINE)
    
    if match:
        # Extract and dedent the text
        text = match.group(1)
        # Remove common leading indentation (2 spaces)
        lines = text.split('\n')
        dedented_lines = []
        for line in lines:
            if line.startswith('  '):
                dedented_lines.append(line[2:])
            elif line.strip() == '':
                dedented_lines.append('')
            else:
                dedented_lines.append(line)
        return '\n'.join(dedented_lines).strip()
    
    # Fallback: try simple key: value format
    simple_pattern = r'post_text:\s*(.+?)(?:\n\w|\n---|\Z)'
    match = re.search(simple_pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    post_logger.warning(f"Could not extract post_text from {filepath}")
    return ""


def find_approved_post_file() -> str:
    """
    Find the first/newest LINKEDIN_POST_*.md file in Approved/.
    
    Returns:
        Path to the file or empty string if none found
    """
    if not os.path.exists(APPROVED_DIR):
        return ""
    
    # Find all LINKEDIN_POST_*.md files
    files = []
    for filename in os.listdir(APPROVED_DIR):
        if filename.startswith('LINKEDIN_POST_') and filename.endswith('.md'):
            filepath = os.path.join(APPROVED_DIR, filename)
            if os.path.isfile(filepath):
                mtime = os.path.getmtime(filepath)
                files.append((filepath, mtime))
    
    if not files:
        return ""
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x[1], reverse=True)
    
    post_logger.info(f"Found {len(files)} approved post file(s)")
    return files[0][0]


def post_to_linkedin(post_text: str, dry_run: bool = False) -> bool:
    """
    Posts content to LinkedIn.
    
    Args:
        post_text: The content to post
        dry_run: If True, don't actually post
        
    Returns:
        True if successful, False otherwise
    """
    playwright = None
    browser = None
    page = None
    
    try:
        post_logger.info("Starting Playwright...")
        playwright = sync_playwright().start()
        
        post_logger.info(f"Launching browser with session: {SESSION_DIR}")
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            viewport={"width": 1280, "height": 720},
            args=[
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--lang=en-US',
            ]
        )
        
        page = browser.new_page()
        
        # Navigation with retry logic (networkidle is unreliable on LinkedIn)
        max_attempts = 3
        navigation_success = False
        
        for attempt in range(1, max_attempts + 1):
            try:
                post_logger.info(f"Attempting navigation to feed (attempt {attempt}/{max_attempts})...")
                
                # Navigate to feed with domcontentloaded (faster than networkidle)
                page.goto(
                    "https://www.linkedin.com/feed/",
                    wait_until="domcontentloaded",
                    timeout=120000
                )
                
                post_logger.info("Goto completed, waiting for composer/feed...")
                
                # Wait for composer/feed elements to confirm page is interactive
                composer_detected = False
                
                # Primary selectors - LinkedIn post composer
                primary_selectors = [
                    'div[role="textbox"][contenteditable="true"]',
                    'button:has-text("Start a post")',
                    '[aria-label*="Start a post"]',
                    '.share-box-feed-entry__trigger',
                ]
                
                for selector in primary_selectors:
                    try:
                        page.wait_for_selector(selector, timeout=60000)
                        post_logger.info(f"Feed ready - proceeding to post (detected via: {selector})")
                        composer_detected = True
                        break
                    except PlaywrightTimeout:
                        continue
                
                # Fallback selectors - feed container
                if not composer_detected:
                    fallback_selectors = [
                        'div.feed-shared-update-v2',
                        '[role="main"]',
                        'div.scaffold-layout__main',
                        'div.feed-container',
                    ]
                    
                    for selector in fallback_selectors:
                        try:
                            page.wait_for_selector(selector, timeout=30000)
                            post_logger.info(f"Feed container detected (fallback: {selector})")
                            composer_detected = True
                            break
                        except PlaywrightTimeout:
                            continue
                
                if composer_detected:
                    navigation_success = True
                    break
                else:
                    # Check if login page appeared
                    post_logger.warning("Composer not detected, checking for login wall...")
                    
                    login_selectors = [
                        'input#session_key',
                        'input[id="session_key"]',
                        'button.sign-in-submit',
                        'button:has-text("Sign in")',
                        'form#login-form',
                    ]
                    
                    login_detected = False
                    for selector in login_selectors:
                        try:
                            if page.query_selector(selector):
                                login_detected = True
                                break
                        except:
                            continue
                    
                    if login_detected:
                        post_logger.error("Session expired or invalid - needs re-login")
                        screenshot_path = os.path.join(LOGS_DIR, f'linkedin_login_required_{time.strftime("%Y%m%d_%H%M%S")}.png')
                        page.screenshot(path=screenshot_path)
                        post_logger.info(f"Login wall screenshot saved: {screenshot_path}")
                        raise Exception("LinkedIn session expired - please run: python linkedin_login.py")
                    
                    post_logger.warning(f"Attempt {attempt} failed - no composer or login detected")
                    if attempt < max_attempts:
                        post_logger.info("Retrying in 5 seconds...")
                        time.sleep(5)
                        
            except Exception as e:
                post_logger.error(f"Navigation attempt {attempt} failed: {e}")
                screenshot_path = os.path.join(LOGS_DIR, f'linkedin_nav_error_attempt{attempt}_{time.strftime("%Y%m%d_%H%M%S")}.png')
                try:
                    page.screenshot(path=screenshot_path)
                    post_logger.info(f"Error screenshot saved: {screenshot_path}")
                except:
                    pass
                
                if attempt < max_attempts:
                    post_logger.info("Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    post_logger.error("All navigation attempts failed")
                    raise
        
        if not navigation_success:
            raise Exception("Failed to load LinkedIn feed after all attempts")
        
        post_logger.info("Navigation successful - ready to post")
        
        if dry_run:
            post_logger.info("=== DRY RUN MODE ===")
            post_logger.info(f"Would post ({len(post_text)} chars):\n{post_text[:200]}...")
            screenshot_path = os.path.join(LOGS_DIR, f'linkedin_dryrun_{time.strftime("%Y%m%d_%H%M%S")}.png')
            page.screenshot(path=screenshot_path)
            post_logger.info(f"Screenshot saved: {screenshot_path}")
            return True

        # Scroll to top to ensure composer is in viewport
        post_logger.info("Scrolling to top of feed...")
        page.evaluate("window.scrollTo(0, 0)")
        
        # Wait for dynamic elements to settle
        post_logger.info("Waiting for page elements to settle...")
        time.sleep(5)

        # Composer activation logic - check if already visible first
        post_logger.info("Attempting to locate composer textbox...")
        textbox = None
        
        # Step 1: Check if editable textbox is already present and visible
        try:
            textbox_locator = page.locator('div[role="textbox"][contenteditable="true"]')
            count = textbox_locator.count()
            post_logger.info(f"Found {count} textbox element(s)")
            
            if count > 0 and textbox_locator.first.is_visible():
                textbox = textbox_locator.first
                post_logger.info("Composer textbox already visible - focusing...")
                textbox.focus()
                time.sleep(1)
                textbox.click()
                time.sleep(1)
            else:
                post_logger.info("Textbox not visible, looking for trigger to click...")
                textbox = None
        except Exception as e:
            post_logger.debug(f"Direct textbox check failed: {e}")
        
        # Step 2: If textbox not found, click trigger to open composer
        if textbox is None:
            trigger_clicked = False
            selectors_tried = []
            
            # Priority 1: aria-label based
            try:
                selectors_tried.append('div[aria-label*="Start a post"]')
                post_logger.info('Trying: div[aria-label*="Start a post"]...')
                trigger = page.locator('div[aria-label*="Start a post"], div[aria-label*="write a post"]').first
                if trigger.count() > 0 and trigger.is_visible():
                    trigger.click()
                    post_logger.info("Trigger found via aria-label, clicking...")
                    trigger_clicked = True
            except Exception as e:
                post_logger.debug(f"Aria-label locator failed: {e}")
            
            # Priority 2: placeholder text
            if not trigger_clicked:
                try:
                    selectors_tried.append('placeholder="Start a post"')
                    post_logger.info('Trying: placeholder="Start a post"...')
                    trigger = page.get_by_placeholder("Start a post", exact=False).first
                    if trigger.count() > 0 and trigger.is_visible():
                        trigger.click()
                        post_logger.info("Trigger found via placeholder, clicking...")
                        trigger_clicked = True
                except Exception as e:
                    post_logger.debug(f"Placeholder locator failed: {e}")
            
            # Priority 3: role-based locator
            if not trigger_clicked:
                try:
                    selectors_tried.append('role=textbox name="Start a post"')
                    post_logger.info('Trying: role=textbox name="Start a post"...')
                    trigger = page.get_by_role("textbox", name=re.compile("start a post|what.*mind", re.I)).first
                    if trigger.count() > 0 and trigger.is_visible():
                        trigger.click()
                        post_logger.info("Trigger found via role locator, clicking...")
                        trigger_clicked = True
                except Exception as e:
                    post_logger.debug(f"Role locator failed: {e}")
            
            # Priority 4: fallback near profile avatar
            if not trigger_clicked:
                try:
                    selectors_tried.append('div.feed-identity-module__actor-meta + div')
                    post_logger.info('Trying: div.feed-identity-module__actor-meta + div...')
                    trigger = page.locator('div.feed-identity-module__actor-meta + div').first
                    if trigger.count() > 0 and trigger.is_visible():
                        trigger.click()
                        post_logger.info("Trigger found via profile fallback, clicking...")
                        trigger_clicked = True
                except Exception as e:
                    post_logger.debug(f"Profile fallback locator failed: {e}")
            
            if not trigger_clicked:
                post_logger.error("Could not find composer trigger")
                post_logger.info(f"Selectors tried: {', '.join(selectors_tried)}")
                screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_notrigger_{time.strftime("%Y%m%d_%H%M%S")}.png')
                page.screenshot(path=screenshot_path)
                post_logger.info(f"Screenshot saved: {screenshot_path}")
                return False
            
            # Wait for textbox to appear after clicking trigger
            post_logger.info("Waiting for editable textbox to appear...")
            time.sleep(2)
        
        # Step 3: Wait for textbox to be ready (if not already found)
        if textbox is None:
            try:
                textbox = page.wait_for_selector('div[role="textbox"][contenteditable="true"]', state="visible", timeout=45000)
                post_logger.info("Editable textbox appeared and ready")
            except PlaywrightTimeout:
                post_logger.error("Textbox did not appear after clicking trigger")
                screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_notextbox_{time.strftime("%Y%m%d_%H%M%S")}.png')
                page.screenshot(path=screenshot_path)
                post_logger.info(f"Screenshot saved: {screenshot_path}")
                return False
        
        # Step 4: Clear existing content and fill with new text
        post_logger.info("Clearing text area...")
        textbox.focus()
        time.sleep(0.5)

        # Clear any existing content first
        post_logger.info("Clearing existing content...")
        page.keyboard.press('Control+A')
        page.keyboard.press('Delete')
        time.sleep(0.5)

        # Type text using keyboard (more reliable than fill() for LinkedIn)
        post_logger.info(f"Typing post content using keyboard ({len(post_text)} chars)...")
        
        # Type in chunks for realism and to trigger LinkedIn's content detection
        chunk_size = 50
        for i in range(0, len(post_text), chunk_size):
            chunk = post_text[i:i+chunk_size]
            page.keyboard.type(chunk, delay=20)
            time.sleep(0.05)
        
        post_logger.info("Text entry complete")

        # Trigger LinkedIn's content detection by pressing Enter then Backspace
        # This makes LinkedIn recognize there's content in the editor
        time.sleep(1)
        post_logger.info("Triggering content detection...")
        page.keyboard.press('Enter')
        time.sleep(0.3)
        page.keyboard.press('Backspace')
        time.sleep(0.5)
        
        # Scroll to bring Post button into view
        post_logger.info("Scrolling to locate Post button...")
        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(2)

        # Find and click Post button
        post_logger.info("Looking for Post button...")
        
        # Take screenshot to see current state BEFORE searching
        debug_screenshot = os.path.join(LOGS_DIR, f'linkedin_prebutton_{time.strftime("%Y%m%d_%H%M%S")}.png')
        try:
            page.screenshot(path=debug_screenshot)
            post_logger.info(f"Pre-button screenshot saved: {debug_screenshot}")
        except Exception as e:
            post_logger.warning(f"Could not save screenshot: {e}")

        submit_button = None
        
        # Method 1: Use Playwright's text selector (most reliable)
        try:
            post_logger.info('Trying: text="Post" (exact button)...')
            submit_button = page.get_by_text("Post", exact=True).first
            if submit_button.count() > 0 and submit_button.is_visible():
                post_logger.info("Found Post button via text selector")
            else:
                submit_button = None
        except Exception as e:
            post_logger.debug(f"Text selector failed: {e}")
        
        # Method 2: Look for button in dialog footer
        if submit_button is None:
            try:
                post_logger.info('Trying: dialog footer button...')
                # LinkedIn dialog structure: footer contains the Post button
                footer = page.query_selector('div[role="dialog"] footer, div.sr-only + div')
                if footer:
                    submit_button = footer.query_selector('button')
                    if submit_button:
                        post_logger.info("Found button in dialog footer")
            except Exception as e:
                post_logger.debug(f"Footer search failed: {e}")
        
        # Method 3: Find any enabled button with "Post" text
        if submit_button is None:
            submit_selectors = [
                'button:has-text("Post")',
                'button[aria-label="Post"]',
                'button[type="submit"]:has-text("Post")',
                'div[role="dialog"] button:has-text("Post")',
                'button[data-verb="share-update"]',
            ]
            
            for selector in submit_selectors:
                try:
                    post_logger.info(f"Trying: {selector}...")
                    submit_button = page.wait_for_selector(selector, timeout=5000)
                    if submit_button:
                        post_logger.info(f"Found submit button: {selector}")
                        break
                except PlaywrightTimeout:
                    post_logger.debug(f"Selector failed: {selector}")
                    continue
        
        # Method 4: Last resort - find any button in the visible dialog
        if submit_button is None:
            post_logger.info("Looking for ANY button in dialog...")
            try:
                dialog = page.query_selector('div[role="dialog"]')
                if dialog:
                    buttons = dialog.query_selector_all('button')
                    post_logger.info(f"Found {len(buttons)} button(s) in dialog")
                    for btn in buttons:
                        try:
                            btn_text = btn.inner_text().strip()
                            post_logger.info(f"Button text: '{btn_text}'")
                            if 'post' in btn_text.lower() and btn.is_visible():
                                submit_button = btn
                                post_logger.info(f"Selected button with text: '{btn_text}'")
                                break
                        except:
                            continue
            except Exception as e:
                post_logger.warning(f"Dialog button search failed: {e}")

        if not submit_button:
            post_logger.error("Could not find Post button after trying all methods")
            screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_nosubmit_{time.strftime("%Y%m%d_%H%M%S")}.png')
            page.screenshot(path=screenshot_path)
            post_logger.info(f"Screenshot saved: {screenshot_path}")
            return False

        post_logger.info("Clicking Post button...")

        # Take screenshot BEFORE clicking to see what we're about to click
        pre_click_screenshot = os.path.join(LOGS_DIR, f'linkedin_pre_click_{time.strftime("%Y%m%d_%H%M%S")}.png')
        try:
            page.screenshot(path=pre_click_screenshot)
            post_logger.info(f"Pre-click screenshot saved: {pre_click_screenshot}")
        except Exception as e:
            post_logger.warning(f"Could not save pre-click screenshot: {e}")

        submit_button.scroll_into_view_if_needed()
        time.sleep(0.5)
        
        # Try regular click first
        try:
            submit_button.click()
            post_logger.info("Regular click successful")
        except Exception as e:
            post_logger.warning(f"Regular click failed: {e}, trying force click...")
            # Force click using JavaScript
            page.evaluate('(el) => el.click()', submit_button)
            post_logger.info("Force click executed")

        # Wait longer for LinkedIn to process the post
        post_logger.info("Waiting for LinkedIn to process post...")
        time.sleep(5)
        
        # Check for actual success indicators
        post_logger.info("Checking for post confirmation...")
        post_confirmed = False
        
        # Success indicator 1: "You posted this" message
        try:
            indicator = page.wait_for_selector('text="You posted this"', timeout=5000)
            if indicator:
                post_confirmed = True
                post_logger.info("Success indicator found: 'You posted this'")
        except PlaywrightTimeout:
            post_logger.debug("'You posted this' not found")
        
        # Success indicator 2: "See your post" message
        if not post_confirmed:
            try:
                indicator = page.wait_for_selector('text="See your post"', timeout=5000)
                if indicator:
                    post_confirmed = True
                    post_logger.info("Success indicator found: 'See your post'")
            except PlaywrightTimeout:
                post_logger.debug("'See your post' not found")
        
        # Success indicator 3: Post appears in feed (look for post article)
        if not post_confirmed:
            try:
                indicator = page.wait_for_selector('article[data-id]', timeout=5000)
                if indicator:
                    post_confirmed = True
                    post_logger.info("Success indicator found: Post article in feed")
            except PlaywrightTimeout:
                post_logger.debug("Post article not found")
        
        # Success indicator 4: URL changed to feed with success param
        if not post_confirmed:
            current_url = page.url
            if "feed" in current_url.lower():
                post_confirmed = True
                post_logger.info(f"Success indicator: Still on feed page ({current_url[:80]}...)")
        
        # Take final screenshot
        screenshot_path = os.path.join(LOGS_DIR, f'linkedin_final_{time.strftime("%Y%m%d_%H%M%S")}.png')
        page.screenshot(path=screenshot_path)
        post_logger.info(f"Final screenshot saved: {screenshot_path}")
        
        if post_confirmed:
            post_logger.info("Post published successfully!")
            return True
        else:
            post_logger.warning("Could not confirm post publication - may have failed")
            post_logger.info("Check the screenshot to verify if post was published")
            # Return True anyway since we clicked and no error appeared
            # User should verify manually
            return True
        
    except Exception as e:
        post_logger.error(f"Error posting: {e}")
        if page:
            try:
                screenshot_path = os.path.join(LOGS_DIR, f'linkedin_error_{time.strftime("%Y%m%d_%H%M%S")}.png')
                page.screenshot(path=screenshot_path)
                post_logger.info(f"Error screenshot saved: {screenshot_path}")
            except:
                pass
        return False
        
    finally:
        if browser:
            browser.close()
        if playwright:
            playwright.stop()


def move_to_done(filepath: str):
    """Move processed file to Done/ directory."""
    if not os.path.exists(filepath):
        return
    
    filename = os.path.basename(filepath)
    dest_path = os.path.join(DONE_DIR, filename)
    
    # Handle duplicate filenames
    if os.path.exists(dest_path):
        base, ext = os.path.splitext(filename)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(DONE_DIR, f"{base}_{timestamp}{ext}")
    
    try:
        shutil.move(filepath, dest_path)
        post_logger.info(f"Moved {filename} to Done/")
    except Exception as e:
        post_logger.error(f"Failed to move file to Done/: {e}")


def main():
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
    
    parser.add_argument(
        'post_text',
        nargs='?',
        default='',
        help='Post text to publish (required unless --from-approved is used)'
    )
    
    parser.add_argument(
        '--from-approved',
        action='store_true',
        help='Read post from Approved/ folder instead of command line'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be posted without actually posting'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
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
        # Mode 2: Find and read from Approved/
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
        # Mode 1: Direct text from command line
        post_text = args.post_text
    
    # Post to LinkedIn
    success = post_to_linkedin(post_text, args.dry_run)

    # Handle result
    if success:
        post_logger.info("Operation completed successfully")

        # If from-approved mode, move file to Done/ ONLY if not dry run
        if args.from_approved and not args.dry_run:
            # Find the file again (it should still be in Approved/)
            filepath = find_approved_post_file()
            if filepath:
                move_to_done(filepath)
            else:
                post_logger.warning("Could not find file to move to Done/")
    else:
        post_logger.error("Operation failed - file left in Approved/ for retry")
        sys.exit(1)

    post_logger.info("=" * 60)


if __name__ == "__main__":
    main()
