import os
import shutil
import time
import logging
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configure logging
os.makedirs('./Logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('filesystem_watcher.log'),
        logging.StreamHandler()
    ]
)

class InboxHandler(FileSystemEventHandler):
    def __init__(self):
        self.needs_action_dir = './Needs_Action'
        self.quarantine_dir = './Quarantine'
        os.makedirs(self.needs_action_dir, exist_ok=True)
        os.makedirs(self.quarantine_dir, exist_ok=True)

    def wait_for_file_stability(self, file_path):
        """Wait for the file size to stop changing before moving."""
        last_size = -1
        max_attempts = 10
        attempts = 0
        while attempts < max_attempts:
            if not os.path.exists(file_path):
                return False
            current_size = os.path.getsize(file_path)
            if current_size == last_size:
                break
            last_size = current_size
            time.sleep(1) # Wait 1 second between size checks
            attempts += 1
        return True

    def on_created(self, event):
        if event.is_directory:
            return

        time.sleep(0.5) # Give the system a moment to fully write the file

        file_path = event.src_path
        filename = os.path.basename(file_path)

        # Skip hidden or temporary files
        if filename.startswith('.') or filename.endswith('.tmp'):
            return

        logging.info(f"New file detected in Inbox: {filename}")

        try:
            # Check if file still exists after initial sleep
            if not os.path.exists(file_path):
                logging.info(f"File {filename} no longer exists in Inbox. Likely handled by another event. Skipping.")
                return

            # 1. Wait until the file is fully written
            if not self.wait_for_file_stability(file_path):
                logging.warning(f"File {filename} disappeared before it could be stabilized. Skipping.")
                return

            new_path = os.path.join(self.needs_action_dir, filename)

            # 2. Prevent overwriting existing files in Needs_Action
            if os.path.exists(new_path):
                logging.warning(f"File '{filename}' already exists in Needs_Action. Skipping copy.")
                return

            # 3. COPY file to Needs_Action (original stays in Inbox)
            shutil.copy2(file_path, new_path)
            
            # Verify copy was successful
            if os.path.exists(new_path) and os.path.getsize(new_path) == os.path.getsize(file_path):
                logging.info(f"Successfully copied {filename} to Needs_Action (original kept in Inbox)")
            else:
                # Copy failed - log error, original stays in Inbox
                logging.error(f"Copy failed for {filename}. Original kept in Inbox.")
                return

            # 4. Create metadata file ONLY after successful move
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            metadata_content = f"""# {filename} Metadata

## Details
- Original filename: {filename}
- Created timestamp: {timestamp}
- Type: file_drop
- Status: pending
"""
            metadata_filename = f"{os.path.splitext(filename)[0]}_metadata.md"
            metadata_path = os.path.join(self.needs_action_dir, metadata_filename)
            
            with open(metadata_path, 'w') as f:
                f.write(metadata_content)
            logging.info(f"Created metadata file: {metadata_filename}")

        except FileNotFoundError:
            logging.info(f"File {filename} not found during move. Likely already processed by another event. Skipping.")
        except Exception as e:
            logging.error(f"Error processing {filename}: {str(e)}")

def main():
    inbox_dir = './Inbox'
    os.makedirs(inbox_dir, exist_ok=True)

    event_handler = InboxHandler()
    observer = Observer()
    observer.schedule(event_handler, inbox_dir, recursive=False)

    logging.info(f"Starting stable filesystem watcher for {inbox_dir}")
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logging.info("Filesystem watcher stopped")

    observer.join()

if __name__ == "__main__":
    main()
