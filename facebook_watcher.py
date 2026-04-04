#!/usr/bin/env python3
"""
Facebook Watcher - Gold Tier Social Media Integration
======================================================
Monitors Facebook for new messages, notifications, and posts with keywords.
Uses Playwright with persistent session for authentication.

Features:
- Persistent browser session (./facebook_session)
- Monitor messages, notifications, and posts
- Keyword detection (urgent, invoice, sales, etc.)
- Create Needs_Action/FB_*.md files for AI processing
- Infinite loop with configurable poll interval
- Logs to Logs/facebook_watcher.log

Usage:
    python facebook_watcher.py

Session Management:
    First run: Login manually in the browser window
    Subsequent runs: Session is reused from ./facebook_session
"""

import os
import sys
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from playwright.async_api import async_playwright, Page, BrowserContext

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
FACEBOOK_URL = "https://www.facebook.com"
SESSION_DIR = PROJECT_ROOT / "facebook_session"
POLL_INTERVAL = 60  # seconds
KEYWORDS = ["urgent", "invoice", "sales", "payment", "order", "customer", "complaint", "review"]
NEEDS_ACTION_DIR = PROJECT_ROOT / "Needs_Action"
LOG_DIR = PROJECT_ROOT / "Logs"

# Ensure directories exist
SESSION_DIR.mkdir(exist_ok=True)
NEEDS_ACTION_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# Setup logging
LOG_FILE = LOG_DIR / "facebook_watcher.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class FacebookWatcher:
    """Monitor Facebook for messages and notifications."""

    def __init__(self):
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.last_message_time: Optional[datetime] = None
        self.last_notification_time: Optional[datetime] = None
        self.processed_items: set = set()

    async def start(self):
        """Start the Facebook watcher."""
        logger.info("Starting Facebook Watcher...")
        logger.info(f"Session directory: {SESSION_DIR}")
        logger.info(f"Monitoring keywords: {KEYWORDS}")
        logger.info(f"Poll interval: {POLL_INTERVAL}s")

        async with async_playwright() as p:
            # Launch browser with persistent context - try system Chrome first
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            try:
                browser = await p.chromium.launch_persistent_context(
                    user_data_dir=str(SESSION_DIR),
                    executable_path=chrome_path,
                    headless=False,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox'
                    ]
                )
                logger.info("Using system Chrome")
            except Exception:
                logger.info("System Chrome not available, using bundled Chromium")
                browser = await p.chromium.launch_persistent_context(
                    user_data_dir=str(SESSION_DIR),
                    headless=False,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox'
                    ]
                )

            # Get the first page or create new one
            if browser.pages:
                self.page = browser.pages[0]
            else:
                self.page = await browser.new_page()

            self.context = browser

            # Navigate to Facebook
            logger.info("Navigating to Facebook...")
            await self.page.goto(FACEBOOK_URL, wait_until='domcontentloaded', timeout=30000)

            # Wait for page to load
            await asyncio.sleep(5)

            # Check if logged in
            is_logged_in = await self.check_login_status()
            if not is_logged_in:
                logger.warning("Not logged in. Please login manually in the browser window.")
                logger.info("Waiting up to 2 minutes for manual login...")
                await asyncio.sleep(120)

            logger.info("Facebook Watcher initialized. Starting monitoring loop...")

            # Main monitoring loop
            await self.monitor_loop()

    async def check_login_status(self) -> bool:
        """Check if user is logged in to Facebook."""
        try:
            # Check for common logged-in indicators
            await self.page.wait_for_selector('[aria-label="Menu"]', timeout=10000)
            return True
        except Exception:
            return False

    async def monitor_loop(self):
        """Main monitoring loop."""
        while True:
            try:
                await self.check_messages()
                await self.check_notifications()
                await asyncio.sleep(POLL_INTERVAL)
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(POLL_INTERVAL)

    async def check_messages(self):
        """Check for new Facebook messages."""
        logger.debug("Checking for new messages...")

        try:
            # Navigate to Messenger
            await self.page.goto(f"{FACEBOOK_URL}/messages", wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)

            # Wait for message list to load
            try:
                await self.page.wait_for_selector('[role="row"]', timeout=10000)
            except Exception:
                logger.debug("No message rows found, may not be logged in or no messages")
                return

            # Get recent messages
            messages = await self.page.query_selector_all('[role="row"]')

            for i, msg in enumerate(messages[:10]):  # Check last 10 messages
                try:
                    # Extract message data
                    text_elem = await msg.query_selector('span[dir="auto"]')
                    if not text_elem:
                        continue

                    text = await text_elem.inner_text()
                    timestamp_elem = await msg.query_selector('abbr')
                    timestamp = await timestamp_elem.get_attribute('data-utime') if timestamp_elem else None

                    # Create unique ID
                    msg_id = f"msg_{i}_{hash(text)}"

                    if msg_id in self.processed_items:
                        continue

                    # Check for keywords
                    matched_keywords = self.check_keywords(text)
                    if matched_keywords:
                        logger.info(f"Message with keywords found: {matched_keywords}")
                        await self.create_action_file(
                            action_type="message",
                            content=text,
                            keywords=matched_keywords,
                            timestamp=timestamp,
                            source="Facebook Messenger"
                        )

                    self.processed_items.add(msg_id)

                    # Keep processed items set bounded
                    if len(self.processed_items) > 1000:
                        self.processed_items = set(list(self.processed_items)[-500:])

                except Exception as e:
                    logger.debug(f"Error processing message: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error checking messages: {e}")

    async def check_notifications(self):
        """Check for new Facebook notifications."""
        logger.debug("Checking for new notifications...")

        try:
            # Navigate to notifications
            await self.page.goto(f"{FACEBOOK_URL}/notifications", wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)

            # Wait for notification list to load
            try:
                await self.page.wait_for_selector('[role="article"]', timeout=10000)
            except Exception:
                logger.debug("No notification rows found")
                return

            # Get recent notifications
            notifications = await self.page.query_selector_all('[role="article"]')

            for i, notif in enumerate(notifications[:10]):  # Check last 10 notifications
                try:
                    # Extract notification data
                    text_elem = await notif.query_selector('span[dir="auto"]')
                    if not text_elem:
                        continue

                    text = await text_elem.inner_text()
                    time_elem = await notif.query_selector('abbr')
                    timestamp = await time_elem.get_attribute('data-utime') if time_elem else None

                    # Create unique ID
                    notif_id = f"notif_{i}_{hash(text)}"

                    if notif_id in self.processed_items:
                        continue

                    # Check for keywords
                    matched_keywords = self.check_keywords(text)
                    if matched_keywords:
                        logger.info(f"Notification with keywords found: {matched_keywords}")
                        await self.create_action_file(
                            action_type="notification",
                            content=text,
                            keywords=matched_keywords,
                            timestamp=timestamp,
                            source="Facebook Notifications"
                        )

                    self.processed_items.add(notif_id)

                    # Keep processed items set bounded
                    if len(self.processed_items) > 1000:
                        self.processed_items = set(list(self.processed_items)[-500:])

                except Exception as e:
                    logger.debug(f"Error processing notification: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error checking notifications: {e}")

    def check_keywords(self, text: str) -> List[str]:
        """Check if text contains any monitored keywords."""
        if not text:
            return []

        text_lower = text.lower()
        matched = [kw for kw in KEYWORDS if kw.lower() in text_lower]
        return matched

    async def create_action_file(self, action_type: str, content: str, keywords: List[str],
                                  timestamp: Optional[str], source: str):
        """Create a Needs_Action file for AI processing."""
        try:
            # Generate filename
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"FB_{action_type.upper()}_{timestamp_str}.md"
            filepath = NEEDS_ACTION_DIR / filename

            # Convert timestamp if provided
            human_time = datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Unknown"

            # Create content
            md_content = f"""# Facebook {action_type.title()} - Needs Action

**Source:** {source}
**Detected:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Original Time:** {human_time}
**Keywords:** {', '.join(keywords)}
**Priority:** {'High' if 'urgent' in keywords else 'Medium'}

---

## Content

```
{content}
```

---

## Suggested Actions

- [ ] Review the message/notification
- [ ] Determine if response is needed
- [ ] Draft appropriate response
- [ ] Take necessary action (invoice, support, etc.)

---

## AI Processing

<!-- AI agent will process this file and suggest actions -->
<!-- Move to Pending_Approval/ when action is determined -->
<!-- Move to Approved/ after action is taken -->
"""

            # Write file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(md_content)

            logger.info(f"Created action file: {filename}")

        except Exception as e:
            logger.error(f"Error creating action file: {e}")


async def main():
    """Main entry point."""
    watcher = FacebookWatcher()
    try:
        await watcher.start()
    except KeyboardInterrupt:
        logger.info("Facebook Watcher stopped by user")
    except Exception as e:
        logger.error(f"Facebook Watcher error: {e}")
        raise
    finally:
        # Cleanup: close browser context properly
        if watcher.context:
            try:
                await watcher.context.close()
                logger.info("Browser context closed")
            except Exception as e:
                logger.debug(f"Error closing browser context: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # Already handled in main()
