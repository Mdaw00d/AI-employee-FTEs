"""
Email Reply Approver - Watches Approved/ for email reply drafts and processes them.

This script monitors the Approved/ directory for files starting with EMAIL_REPLY_.
When found, it extracts the reply details and (for now) logs what would be sent.

Future enhancement: Add actual email sending with gmail.send scope.

================================================================================
FIRST RUN SETUP
================================================================================
1. Ensure the Approved/ directory exists
2. Run: python email_reply_approver.py
3. Script will watch for approved reply drafts

================================================================================
PERSISTENT OPERATION
================================================================================
Using PM2:
    pm2 start email_reply_approver.py --interpreter python --name email-approver

Using Python directly:
    python email_reply_approver.py

To stop:
    pm2 stop email-approver
    pm2 delete email-approver

================================================================================
WORKFLOW
================================================================================
1. AI creates reply draft in Pending_Approval/EMAIL_REPLY_*.md
2. User reviews and moves file to Approved/
3. This script detects the file and processes it
4. Currently: Logs what would be sent, moves to Done/
5. Future: Actually send email via Gmail API

================================================================================
"""

import os
import sys
import time
import logging
import shutil
import re
import random
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ============================================================================
# Configuration
# ============================================================================

# Directories
APPROVED_DIR = './Approved'
DONE_DIR = './Done'
LOGS_DIR = './Logs'
PENDING_APPROVAL_DIR = './Pending_Approval'

# Ensure directories exist
for directory in [APPROVED_DIR, DONE_DIR, LOGS_DIR, PENDING_APPROVAL_DIR]:
    os.makedirs(directory, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'email_reply_approver.log'), encoding='utf-8'),
        logging.StreamHandler()
    ],
    force=True
)

# Force UTF-8 encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Processing interval in seconds
CHECK_INTERVAL = 30

# Maximum retries
MAX_RETRIES = 3
BASE_BACKOFF = 5


# ============================================================================
# Email Draft Parsing
# ============================================================================

def parse_email_reply_draft(content: str) -> dict:
    """
    Parse an email reply draft file to extract metadata and body.
    
    Args:
        content: Full content of the draft file
        
    Returns:
        Dictionary with email fields
    """
    email_data = {
        'to': '',
        'subject': '',
        'body': '',
        'original_message_id': '',
        'classification': '',
        'priority': 'medium',
        'type': ''
    }
    
    try:
        # Extract frontmatter
        frontmatter_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)
            
            # Parse key-value pairs
            for line in frontmatter.split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if key in email_data:
                        email_data[key] = value
            
            # Extract body (everything after frontmatter)
            body_match = re.search(r'^---\s*\n.*?\n---\s*\n(.*)', content, re.DOTALL)
            if body_match:
                email_data['body'] = body_match.group(1).strip()
        else:
            # No frontmatter - try to extract from content
            email_data['body'] = content.strip()
            
    except Exception as e:
        logging.error(f"Failed to parse email draft: {e}")
        email_data['body'] = content
        email_data['error'] = str(e)
    
    return email_data


def process_approved_reply(file_path: str) -> bool:
    """
    Process an approved email reply draft.
    
    Currently logs what would be sent. Future: actually send via Gmail API.
    
    Args:
        file_path: Path to the approved draft file
        
    Returns:
        True if processed successfully, False otherwise
    """
    filename = os.path.basename(file_path)
    
    logging.info(f"Processing approved reply: {filename}")
    
    try:
        # Read the draft file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the draft
        email_data = parse_email_reply_draft(content)
        
        # Log what would be sent
        logging.info("=" * 60)
        logging.info("EMAIL REPLY APPROVED - WOULD SEND:")
        logging.info("=" * 60)
        logging.info(f"To: {email_data.get('to', 'Unknown')}")
        logging.info(f"Subject: {email_data.get('subject', 'No Subject')}")
        logging.info(f"Classification: {email_data.get('classification', 'Unknown')}")
        logging.info(f"Priority: {email_data.get('priority', 'medium')}")
        logging.info("-" * 60)
        logging.info("Body:")
        logging.info(email_data.get('body', '(No body)'))
        logging.info("=" * 60)
        
        # Print to console as well
        print(f"\n{'='*60}")
        print(f"✓ EMAIL REPLY APPROVED")
        print(f"{'='*60}")
        print(f"To: {email_data.get('to', 'Unknown')}")
        print(f"Subject: {email_data.get('subject', 'No Subject')}")
        print(f"{'='*60}")
        print(f"Body preview:")
        body_preview = email_data.get('body', '')[:300]
        if len(email_data.get('body', '')) > 300:
            body_preview += '...'
        print(body_preview)
        print(f"{'='*60}")
        print(f"[LOGGED] Would send reply - Gmail send not yet implemented")
        print(f"{'='*60}\n")
        
        # Log to daily log
        log_date = datetime.now().strftime('%Y-%m-%d')
        log_path = os.path.join(LOGS_DIR, f'{log_date}_emails.md')
        with open(log_path, 'a', encoding='utf-8') as log_file:
            log_file.write(f"\n## {datetime.now().strftime('%H:%M:%S')} - Email Reply Sent\n")
            log_file.write(f"**To:** {email_data.get('to', 'Unknown')}\n")
            log_file.write(f"**Subject:** {email_data.get('subject', 'No Subject')}\n")
            log_file.write(f"**Classification:** {email_data.get('classification', 'Unknown')}\n")
            log_file.write(f"**Status:** Logged (send not implemented)\n")
            log_file.write(f"**Source File:** {filename}\n")
            log_file.write("---\n")
        
        # Move to Done directory
        done_path = os.path.join(DONE_DIR, filename)
        
        # Handle duplicate filenames
        if os.path.exists(done_path):
            base, ext = os.path.splitext(filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_filename = f"{base}_{timestamp}{ext}"
            done_path = os.path.join(DONE_DIR, new_filename)
            logging.info(f"File exists in Done, using new name: {new_filename}")
        
        shutil.copy2(file_path, done_path)
        
        if os.path.exists(done_path):
            os.remove(file_path)
            logging.info(f"Moved {filename} to Done/")
        else:
            logging.error(f"Failed to move {filename} to Done/")
            return False
        
        return True
        
    except Exception as e:
        logging.error(f"Failed to process {filename}: {e}")
        return False


class ApprovedHandler(FileSystemEventHandler):
    """Watches Approved/ directory for new email reply drafts."""
    
    def __init__(self):
        self.processing_lock = False
        self.processed_files = set()
    
    def wait_for_file_stability(self, file_path: str, max_attempts: int = 10) -> bool:
        """Wait for file size to stabilize before processing."""
        last_size = -1
        for _ in range(max_attempts):
            if not os.path.exists(file_path):
                return False
            current_size = os.path.getsize(file_path)
            if current_size == last_size:
                return True
            last_size = current_size
            time.sleep(0.5)
        return True
    
    def on_created(self, event):
        """Handle new files in Approved/."""
        if event.is_directory:
            return
        
        file_path = event.src_path
        filename = os.path.basename(file_path)
        
        # Only process EMAIL_REPLY_ files
        if not filename.startswith('EMAIL_REPLY_'):
            logging.debug(f"Skipping non-email file: {filename}")
            return
        
        # Skip if already processed
        if filename in self.processed_files:
            logging.debug(f"File already processed: {filename}")
            return
        
        logging.info(f"New approved email reply detected: {filename}")
        
        # Wait for file to be fully written
        time.sleep(0.5)
        if not self.wait_for_file_stability(file_path):
            logging.warning(f"File {filename} not stable, skipping")
            return
        
        # Prevent concurrent processing
        if self.processing_lock:
            logging.info(f"Processor busy, will retry {filename}")
            return
        
        try:
            self.processing_lock = True
            if process_approved_reply(file_path):
                self.processed_files.add(filename)
        finally:
            self.processing_lock = False
    
    def on_moved(self, event):
        """Handle files moved into Approved/."""
        if event.is_directory:
            return
        
        dest_path = event.dest_path
        filename = os.path.basename(dest_path)
        
        # Only process EMAIL_REPLY_ files
        if not filename.startswith('EMAIL_REPLY_'):
            return
        
        # Skip if already processed
        if filename in self.processed_files:
            return
        
        logging.info(f"Email reply moved to Approved: {filename}")
        
        # Process after short delay
        time.sleep(0.5)
        
        if self.processing_lock:
            return
        
        try:
            self.processing_lock = True
            if process_approved_reply(dest_path):
                self.processed_files.add(filename)
        finally:
            self.processing_lock = False


def process_all_approved():
    """Process all EMAIL_REPLY_ files currently in Approved/."""
    if not os.path.exists(APPROVED_DIR):
        logging.info("Approved directory does not exist")
        return
    
    # Get all EMAIL_REPLY_ files
    all_files = os.listdir(APPROVED_DIR)
    email_files = [f for f in all_files 
                   if f.startswith('EMAIL_REPLY_') and 
                   os.path.isfile(os.path.join(APPROVED_DIR, f))]
    
    if not email_files:
        logging.debug("No pending email replies in Approved/")
        return
    
    logging.info(f"Found {len(email_files)} approved email reply/ies")
    
    for filename in email_files:
        file_path = os.path.join(APPROVED_DIR, filename)
        process_approved_reply(file_path)


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main email reply approver loop."""
    logging.info("=" * 60)
    logging.info("Email Reply Approver starting...")
    logging.info(f"Watching: {APPROVED_DIR}/")
    logging.info(f"Check interval: {CHECK_INTERVAL} seconds")
    logging.info("=" * 60)
    
    # Process any existing files first
    logging.info("Processing existing approved replies...")
    process_all_approved()
    
    # Setup watchdog
    logging.info(f"Starting watchdog on {APPROVED_DIR}/")
    event_handler = ApprovedHandler()
    observer = Observer()
    observer.schedule(event_handler, APPROVED_DIR, recursive=False)
    observer.start()
    
    logging.info("Email Reply Approver is now watching for approved replies...")
    logging.info("Move EMAIL_REPLY_*.md files to Approved/ to process")
    logging.info("Press Ctrl+C to stop")
    
    retry_count = 0
    
    while True:
        try:
            # Periodic check in case watchdog misses anything
            time.sleep(CHECK_INTERVAL)
            
            # Reset retry count
            retry_count = 0
            
        except Exception as e:
            retry_count += 1
            logging.error(f"Error in watcher loop (attempt {retry_count}/{MAX_RETRIES}): {e}")
            
            if retry_count <= MAX_RETRIES:
                backoff_time = min(BASE_BACKOFF * (2 ** (retry_count - 1)), 60)
                jitter = random.uniform(0, backoff_time * 0.1)
                total_wait = backoff_time + jitter
                
                logging.info(f"Retrying in {total_wait:.1f} seconds...")
                time.sleep(total_wait)
            else:
                logging.error("Max retries exceeded, continuing...")
                retry_count = 0
    
    observer.join()
    logging.info("Email Reply Approver shutdown complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Email Reply Approver stopped by user")
    except Exception as e:
        logging.critical(f"Fatal error: {e}")
        raise
