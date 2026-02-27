"""
WhatsApp Watcher - Monitors WhatsApp Web for unread messages requiring action.

Dependencies:
    pip install playwright pyyaml
    playwright install  # Install browsers

Usage:
    python whatsapp_watcher.py

Note: First run requires manual QR code scan at WhatsApp Web.
      Session is persisted in ./whatsapp_session for subsequent runs.
"""

import os
import time
import logging
import hashlib
import random
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configure logging
os.makedirs('./Logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./Logs/whatsapp_watcher.log'),
        logging.StreamHandler()
    ]
)

# Keywords that indicate a message needs action
ACTION_KEYWORDS = ['urgent', 'invoice', 'payment', 'asap', 'quote', 'help']

# Retry configuration
MAX_RETRIES = 5
BASE_BACKOFF = 5  # seconds


def create_needs_action_file(chat_id: str, chat_name: str, message_text: str) -> str:
    """
    Creates a task file in Needs_Action directory for messages requiring attention.
    
    Args:
        chat_id: Unique identifier for the chat
        chat_name: Display name of the chat/contact
        message_text: The message content that triggered the action
        
    Returns:
        Path to the created file
    """
    needs_action_dir = './Needs_Action'
    os.makedirs(needs_action_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    chat_hash = hashlib.md5(chat_id.encode()).hexdigest()[:8]
    filename = f"WHATSAPP_{timestamp}_{chat_hash}.md"
    filepath = os.path.join(needs_action_dir, filename)
    
    # Generate suggested actions based on keywords found
    matched_keywords = [kw for kw in ACTION_KEYWORDS if kw in message_text.lower()]
    suggested_actions = []
    
    if 'urgent' in matched_keywords or 'asap' in matched_keywords:
        suggested_actions.append("- [ ] Respond within 1 hour")
        suggested_actions.append("- [ ] Assess priority level")
    if 'invoice' in matched_keywords or 'payment' in matched_keywords:
        suggested_actions.append("- [ ] Verify invoice details")
        suggested_actions.append("- [ ] Check payment status")
        suggested_actions.append("- [ ] Forward to finance if needed")
    if 'quote' in matched_keywords:
        suggested_actions.append("- [ ] Prepare quotation")
        suggested_actions.append("- [ ] Review pricing")
    if 'help' in matched_keywords:
        suggested_actions.append("- [ ] Understand the request")
        suggested_actions.append("- [ ] Provide assistance or escalate")
    
    # Default action if no specific matches
    if not suggested_actions:
        suggested_actions.append("- [ ] Review and respond")
    
    content = f"""---
source: WhatsApp
chat_id: {chat_id}
chat_name: {chat_name}
timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
keywords: {', '.join(matched_keywords)}
status: pending
---

# WhatsApp Message Requiring Action

## Contact
**Name:** {chat_name}

## Message
{message_text}

## Suggested Actions
{chr(10).join(suggested_actions)}

## Notes
_Add any additional context or actions below_

"""
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logging.info(f"Created task file: {filename}")
    return filepath


def wait_for_chat_list(page, timeout: int = 30000) -> bool:
    """
    Waits for the WhatsApp Web chat list to be visible.
    
    Args:
        page: Playwright page object
        timeout: Maximum wait time in milliseconds
        
    Returns:
        True if chat list is visible, False otherwise
    """
    try:
        # WhatsApp Web uses different selectors; try multiple patterns
        selectors = [
            'div[role="navigation"]',  # Main chat list container
            'div[data-testid="default-user"]',  # Default view
            'span[title]',  # Chat entries with titles
        ]
        
        for selector in selectors:
            try:
                page.wait_for_selector(selector, timeout=timeout)
                logging.info(f"Chat list visible (detected via: {selector})")
                return True
            except PlaywrightTimeout:
                continue
        
        logging.warning("Could not detect chat list with standard selectors")
        return False
        
    except Exception as e:
        logging.error(f"Error waiting for chat list: {e}")
        return False


def scan_unread_chats(page) -> list:
    """
    Scans for chats with unread messages.
    
    Args:
        page: Playwright page object
        
    Returns:
        List of dicts with chat_id, chat_name, and last_message
    """
    unread_chats = []
    
    try:
        # JavaScript to extract chat information from WhatsApp Web
        extract_chats_script = """
        () => {
            const chats = [];
            // Find all chat list items
            const chatElements = document.querySelectorAll('div[role="listitem"]');
            
            chatElements.forEach((el, index) => {
                // Check for unread indicator
                const unreadBadge = el.querySelector('span[data-testid="unread-chat-count"]');
                const hasUnread = unreadBadge !== null;
                
                if (hasUnread) {
                    const titleEl = el.querySelector('span[title]');
                    const messageEl = el.querySelector('span[data-testid="message-preview"]');
                    
                    if (titleEl && messageEl) {
                        chats.push({
                            chat_id: 'chat_' + index + '_' + Date.now(),
                            chat_name: titleEl.getAttribute('title') || titleEl.textContent,
                            last_message: messageEl.textContent || ''
                        });
                    }
                }
            });
            
            return chats;
        }
        """
        
        chats = page.evaluate(extract_chats_script)
        
        if not chats:
            # Fallback: try alternative selector pattern
            fallback_script = """
            () => {
                const chats = [];
                const chatElements = document.querySelectorAll('div[data-testid="chat-list"] div[role="listitem"]');
                
                chatElements.forEach((el, index) => {
                    const unreadBadge = el.querySelector('span[data-testid="unread-chat-count"], .akpkn');
                    const hasUnread = unreadBadge !== null;
                    
                    if (hasUnread) {
                        const titleEl = el.querySelector('span[title]');
                        const messageEl = el.querySelector('span[data-testid="message-preview"]');
                        
                        if (titleEl && messageEl) {
                            chats.push({
                                chat_id: 'chat_' + index + '_' + Date.now(),
                                chat_name: titleEl.getAttribute('title') || titleEl.textContent,
                                last_message: messageEl.textContent || ''
                            });
                        }
                    }
                });
                
                return chats;
            }
            """
            chats = page.evaluate(fallback_script)
        
        unread_chats = chats
        
    except Exception as e:
        logging.error(f"Error scanning chats: {e}")
    
    return unread_chats


def main():
    """Main WhatsApp watcher loop."""
    logging.info("=" * 60)
    logging.info("WhatsApp Watcher starting...")
    logging.info("Session directory: ./whatsapp_session")
    logging.info("Monitoring for keywords: %s", ', '.join(ACTION_KEYWORDS))
    logging.info("=" * 60)
    
    user_data_dir = os.path.abspath("./whatsapp_session")
    os.makedirs(user_data_dir, exist_ok=True)
    
    retry_count = 0
    
    with sync_playwright() as p:
        # Launch browser in headless mode with persistent context
        # Set headless=False for first run to scan QR code
        browser = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            viewport={"width": 1280, "height": 720},
            args=[
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ]
        )
        
        context = browser
        page = context.new_page()
        
        logging.info("Navigating to WhatsApp Web...")
        page.goto("https://web.whatsapp.com", wait_until="networkidle")
        
        # Wait for chat list (handles both fresh login and authenticated sessions)
        logging.info("Waiting for WhatsApp Web to load...")
        wait_for_chat_list(page, timeout=60000)
        
        logging.info("WhatsApp Watcher is now monitoring for unread messages...")
        logging.info("Scan interval: 45-90 seconds (random)")
        
        while True:
            try:
                # Scan for unread chats
                unread_chats = scan_unread_chats(page)
                
                if unread_chats:
                    logging.info(f"Found {len(unread_chats)} unread chat(s)")
                    
                    for chat in unread_chats:
                        message_lower = chat['last_message'].lower()
                        
                        # Check if message contains action keywords
                        if any(keyword in message_lower for keyword in ACTION_KEYWORDS):
                            logging.info(
                                f"Action required - Chat: {chat['chat_name']}, "
                                f"Message: {chat['last_message'][:50]}..."
                            )
                            
                            try:
                                create_needs_action_file(
                                    chat_id=chat['chat_id'],
                                    chat_name=chat['chat_name'],
                                    message_text=chat['last_message']
                                )
                            except Exception as e:
                                logging.error(f"Failed to create task file: {e}")
                        else:
                            logging.debug(
                                f"Skipping (no keywords) - Chat: {chat['chat_name']}"
                            )
                else:
                    logging.debug("No unread messages found")
                
                # Reset retry count on success
                retry_count = 0
                
            except Exception as e:
                retry_count += 1
                logging.error(f"Error during scan (attempt {retry_count}/{MAX_RETRIES}): {e}")
                
                # Exponential backoff with jitter
                if retry_count <= MAX_RETRIES:
                    backoff_time = min(BASE_BACKOFF * (2 ** (retry_count - 1)), 300)
                    jitter = random.uniform(0, backoff_time * 0.1)
                    total_wait = backoff_time + jitter
                    
                    logging.info(f"Retrying in {total_wait:.1f} seconds...")
                    time.sleep(total_wait)
                    
                    # Try to recover by reloading page
                    try:
                        logging.info("Attempting to recover by reloading WhatsApp Web...")
                        page.reload(wait_until="networkidle")
                        wait_for_chat_list(page, timeout=30000)
                    except Exception as reload_error:
                        logging.error(f"Recovery failed: {reload_error}")
                else:
                    logging.error("Max retries exceeded. Attempting full restart...")
                    retry_count = 0
                    
                    try:
                        browser.close()
                        browser = p.chromium.launch_persistent_context(
                            user_data_dir=user_data_dir,
                            headless=True,
                            viewport={"width": 1280, "height": 720},
                            args=['--disable-gpu', '--disable-dev-shm-usage']
                        )
                        context = browser
                        page = context.new_page()
                        page.goto("https://web.whatsapp.com", wait_until="networkidle")
                    except Exception as restart_error:
                        logging.error(f"Restart failed: {restart_error}")
                        time.sleep(60)
            
            # Random sleep between 45-90 seconds
            sleep_time = random.uniform(45, 90)
            logging.debug(f"Next scan in {sleep_time:.0f} seconds")
            time.sleep(sleep_time)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("WhatsApp Watcher stopped by user")
    except Exception as e:
        logging.critical(f"Fatal error: {e}")
        raise
