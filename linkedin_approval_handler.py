"""
LinkedIn Approval Handler - Watches for approved LinkedIn posts and publishes them automatically.

Dependencies:
    pip install playwright pyyaml watchdog

Usage:
    python linkedin_approval_handler.py

Environment Variables:
    DRY_RUN=true          # Set to 'false' to actually publish posts
    LINKEDIN_SESSION=./linkedin_session

Workflow:
    1. Watches Pending_Approval/ directory
    2. When file moved to Approved/ with LINKEDIN_POST_ prefix:
       - Reads post_text from frontmatter
       - Opens LinkedIn with persistent session
       - Posts the content
       - Logs result
       - Moves approval file to Done/
"""

import os
import sys
import re
import time
import logging
import hashlib
import random
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
LINKEDIN_SESSION_DIR = os.getenv("LINKEDIN_SESSION", "./linkedin_session")
PENDING_APPROVAL_DIR = "./Pending_Approval"
APPROVED_DIR = "./Approved"
DONE_DIR = "./Done"
LOGS_DIR = "./Logs"

# Create directories
for directory in [PENDING_APPROVAL_DIR, APPROVED_DIR, DONE_DIR, LOGS_DIR, LINKEDIN_SESSION_DIR]:
    os.makedirs(directory, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'linkedin_approval_handler.log')),
        logging.StreamHandler()
    ]
)


def parse_frontmatter(content: str) -> dict:
    """
    Parse YAML-like frontmatter from markdown file.
    
    Args:
        content: Full file content with frontmatter
        
    Returns:
        Dictionary of frontmatter fields
    """
    frontmatter = {}
    
    # Match content between --- markers
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
    
    if not match:
        return frontmatter
    
    fm_text = match.group(1)
    
    # Parse key: value pairs
    current_key = None
    current_value = []
    in_multiline = False
    
    for line in fm_text.split('\n'):
        # Check for key: value pattern
        key_match = re.match(r'^(\w+):\s*(.*)', line)
        
        if key_match:
            # Save previous key if exists
            if current_key:
                frontmatter[current_key] = '\n'.join(current_value).strip()
            
            current_key = key_match.group(1)
            value = key_match.group(2).strip()
            
            # Check for multiline value (|)
            if value == '|':
                in_multiline = True
                current_value = []
            else:
                frontmatter[current_key] = value
                current_key = None
                in_multiline = False
        elif in_multiline and current_key:
            # Handle multiline content (remove common leading indent)
            stripped = line[2:] if line.startswith('  ') else line
            current_value.append(stripped)
    
    # Save last key if multiline
    if current_key and current_value:
        frontmatter[current_key] = '\n'.join(current_value).strip()
    
    return frontmatter


def read_approval_file(filepath: str) -> dict:
    """
    Read and parse an approval request file.
    
    Args:
        filepath: Path to the approval file
        
    Returns:
        Dictionary with file metadata and post_text
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    frontmatter = parse_frontmatter(content)
    
    return {
        'filepath': filepath,
        'filename': os.path.basename(filepath),
        'type': frontmatter.get('type', ''),
        'action': frontmatter.get('action', ''),
        'draft_file': frontmatter.get('draft_file', ''),
        'post_text': frontmatter.get('post_text', ''),
        'character_count': frontmatter.get('character_count', ''),
        'created': frontmatter.get('created', ''),
        'status': frontmatter.get('status', 'pending')
    }


def post_to_linkedin(page, post_text: str) -> bool:
    """
    Posts content to LinkedIn using subprocess to avoid asyncio issues.
    
    Args:
        page: Unused (kept for API compatibility)
        post_text: The content to post
        
    Returns:
        True if post was successful, False otherwise
    """
    try:
        logging.info("Starting LinkedIn post via subprocess...")
        
        # Build command
        cmd = [
            sys.executable,  # Current Python interpreter
            "linkedin_poster.py",
            post_text,
        ]
        
        if DRY_RUN:
            cmd.append("--dry-run")
        
        logging.info(f"Running: {' '.join(cmd[:3])}... (post text truncated)")
        
        # Run as subprocess
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        # Log output
        if result.stdout:
            logging.info(f"Poster output: {result.stdout[:500]}")
        if result.stderr:
            logging.error(f"Poster errors: {result.stderr[:500]}")
        
        success = result.returncode == 0
        
        if success:
            logging.info("Post published successfully!")
        else:
            logging.error(f"Post failed with return code {result.returncode}")
        
        return success
        
    except subprocess.TimeoutExpired:
        logging.error("Post timed out after 120 seconds")
        return False
    except Exception as e:
        logging.error(f"Error posting to LinkedIn: {e}")
        return False


class ApprovalHandler(FileSystemEventHandler):
    """Watches Approved/ directory for new LinkedIn post approvals."""
    
    def __init__(self):
        self._processing_lock = False
        
    def process_approved_file(self, filepath: str):
        """Process an approved LinkedIn post file."""
        filename = os.path.basename(filepath)
        
        # Only process LINKEDIN_POST_ files
        if not filename.startswith('LINKEDIN_POST_'):
            logging.debug(f"Skipping non-LinkedIn file: {filename}")
            return
        
        logging.info(f"Processing approved file: {filename}")
        
        try:
            # Read the approval file
            approval_data = read_approval_file(filepath)
            
            # Validate it's a LinkedIn post approval
            if approval_data.get('action') != 'post_linkedin':
                logging.warning(f"File {filename} is not a LinkedIn post action")
                return
            
            post_text = approval_data.get('post_text', '')
            
            if not post_text:
                logging.error(f"No post_text found in {filename}")
                self.move_to_done(filepath, filename, success=False, error="No post text")
                return
            
            logging.info(f"Post content ({len(post_text)} chars): {post_text[:100]}...")
            
            # Post to LinkedIn via subprocess
            if DRY_RUN:
                logging.info("=== DRY RUN MODE ===")
                logging.info(f"Would post:\n{post_text}")
                success = True
            else:
                success = post_to_linkedin(None, post_text)  # page=None since we use subprocess now
            
            # Handle result
            if success:
                logging.info(f"Successfully processed: {filename}")
                self.move_to_done(filepath, filename, success=True)
            else:
                logging.error(f"Failed to post: {filename}")
                self.move_to_done(filepath, filename, success=False)
                
        except Exception as e:
            logging.error(f"Error processing {filename}: {e}")
            self.move_to_done(filepath, filename, success=False, error=str(e))
    
    def move_to_done(self, source_path: str, filename: str, success: bool, error: str = ''):
        """Move processed file to Done/ with result metadata."""
        try:
            # Read original content
            with open(source_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Add result metadata
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            result_section = f"""
---
## Processing Result
- Processed: {timestamp}
- Success: {success}
- Error: {error if error else 'None'}
- DRY_RUN: {DRY_RUN}
"""
            # Append result to content
            updated_content = content.rstrip() + result_section
            
            # Write to Done/
            done_path = os.path.join(DONE_DIR, filename)
            with open(done_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            # Remove from Approved/
            os.remove(source_path)
            
            status = "successfully" if success else "with errors"
            logging.info(f"Moved {filename} to Done/ ({status})")
            
        except Exception as e:
            logging.error(f"Failed to move {filename} to Done/: {e}")
    
    def on_created(self, event):
        """Handle new files in Approved/ directory."""
        if event.is_directory:
            return
        
        file_path = event.src_path
        directory = os.path.dirname(file_path)
        
        # Only process files directly in Approved/
        if os.path.basename(directory) != 'Approved':
            return
        
        # Wait for file to be fully written
        time.sleep(0.5)
        
        if os.path.exists(file_path):
            # Process in a separate thread to avoid asyncio issues
            threading.Thread(target=self._process_file_thread, args=(file_path,), daemon=True).start()
    
    def on_moved(self, event):
        """Handle files moved to Approved/ directory."""
        if event.is_directory:
            return
        
        dest_path = event.dest_path
        directory = os.path.dirname(dest_path)
        
        # Only process files moved to Approved/
        if os.path.basename(directory) != 'Approved':
            return
        
        # Wait for file system to settle
        time.sleep(0.5)
        
        if os.path.exists(dest_path):
            # Process in a separate thread to avoid asyncio issues
            threading.Thread(target=self._process_file_thread, args=(dest_path,), daemon=True).start()
    
    def _process_file_thread(self, file_path: str):
        """Thread wrapper for processing files."""
        if self._processing_lock:
            logging.info("Processor busy, skipping")
            return
        
        try:
            self._processing_lock = True
            self.process_approved_file(file_path)
        finally:
            self._processing_lock = False


def main():
    """Main watcher loop."""
    logging.info("=" * 60)
    logging.info("LinkedIn Approval Handler starting...")
    logging.info(f"DRY_RUN mode: {DRY_RUN}")
    logging.info(f"Watching: {APPROVED_DIR}/")
    logging.info(f"Session: {LINKEDIN_SESSION_DIR}/")
    logging.info("=" * 60)
    
    # Process any existing files in Approved/
    handler = ApprovalHandler()
    
    if os.path.exists(APPROVED_DIR):
        existing_files = [f for f in os.listdir(APPROVED_DIR) if f.startswith('LINKEDIN_POST_')]
        if existing_files:
            logging.info(f"Found {len(existing_files)} existing file(s) to process")
            for filename in existing_files:
                filepath = os.path.join(APPROVED_DIR, filename)
                handler.process_approved_file(filepath)
    
    # Setup watchdog
    event_handler = handler
    observer = Observer()
    observer.schedule(event_handler, APPROVED_DIR, recursive=False)
    
    logging.info(f"Starting watcher on {APPROVED_DIR}/")
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Stopping LinkedIn Approval Handler...")
        observer.stop()
    
    observer.join()
    logging.info("LinkedIn Approval Handler stopped")


if __name__ == "__main__":
    main()
