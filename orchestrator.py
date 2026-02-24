import os
import shutil
import time
import subprocess
import logging
from datetime import datetime
import re

# Configure logging
os.makedirs('./Logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('./Logs/orchestrator.log'),
        logging.StreamHandler()
    ]
)

def update_dashboard(processed_file_names, processed_count):
    """
    Ensures Dashboard.md is updated with:
    - Accurate Pending Tasks Count (based on folder state)
    - Incremented Completed Tasks Count
    - Current Last Processed timestamp
    - New recent activity entries
    """
    dashboard_path = "Dashboard.md"
    needs_action_dir = "Needs_Action"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Calculate current pending (excluding metadata)
    pending_count = 0
    if os.path.exists(needs_action_dir):
        pending_count = len([f for f in os.listdir(needs_action_dir) 
                            if os.path.isfile(os.path.join(needs_action_dir, f)) 
                            and not f.endswith('_metadata.md')])

    # Read existing content
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r") as f:
            lines = f.readlines()
    else:
        # Create a default template if Dashboard.md does not exist
        lines = [
            "# Dashboard\n",
            "\n",
            "## System Status\n",
            "System operational\n",
            "\n",
            "## Pending Tasks Count\n",
            "0\n",
            "\n",
            "## Completed Tasks Count\n",
            "0\n",
            "\n",
            "## Last Processed\n",
            "Never\n",
            "\n",
            "## Recent Activity\n"
        ]

    new_lines = []
    # Flags to indicate if we've handled the line for replacement (e.g., old count)
    skip_next_line = False

    for i, line in enumerate(lines):
        if skip_next_line:
            skip_next_line = False
            continue

        if "## Pending Tasks Count" in line:
            new_lines.append(line)
            new_lines.append(str(pending_count) + "\n")
            skip_next_line = True # Skip the original count line
        elif "## Completed Tasks Count" in line:
            new_lines.append(line)
            current_completed = 0
            # Try to parse the current completed count from the next line
            if i + 1 < len(lines) and re.match(r'^\d+$', lines[i+1].strip()):
                current_completed = int(lines[i+1].strip())
            new_lines.append(str(current_completed + processed_count) + "\n")
            skip_next_line = True # Skip the original count line
        elif "## Last Processed" in line:
            new_lines.append(line)
            new_lines.append(now + "\n")
            skip_next_line = True # Skip the original timestamp line
        elif "## Recent Activity" in line:
            new_lines.append(line)
            # Append new activity entries directly after the header
            for name in processed_file_names:
                new_lines.append(f"- {now}: Processed file '{name}'\n")
            # Now append any *existing* activity entries that follow the header
            for j in range(i + 1, len(lines)):
                if lines[j].strip().startswith('##'): # Stop if next section header is found
                    # Prepend this header for later processing
                    new_lines.append(lines[j])
                    break
                if lines[j].strip(): # Only append non-empty, non-header lines
                    new_lines.append(lines[j])
            break # Stop processing lines after handling Recent Activity section
        else:
            new_lines.append(line)
    
    # Ensure a single trailing newline and no excessive leading/trailing whitespace
    final_content = "".join(new_lines).strip() + "\n"

    with open(dashboard_path, "w") as f:
        f.write(final_content)


def process_needs_action():
    needs_action_dir = "Needs_Action"
    done_dir = "Done"
    os.makedirs(done_dir, exist_ok=True)

    if not os.path.exists(needs_action_dir):
        # If Needs_Action doesn't exist, ensure dashboard pending count is correct and return
        update_dashboard([], 0)
        return

    all_files = os.listdir(needs_action_dir)
    primary_files = [f for f in all_files if not f.endswith('_metadata.md')]
    
    if not primary_files:
        update_dashboard([], 0) # Update pending count to 0 if no files
        return

    processed_count = 0
    processed_file_names = []
    for filename in primary_files:
        file_path = os.path.join(needs_action_dir, filename)
        meta_path = os.path.join(needs_action_dir, f"{os.path.splitext(filename)[0]}_metadata.md")

        logging.info(f"Starting task: {filename}")

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Skip empty files
            if not content.strip():
                logging.warning(f"Skipping empty file: {filename}")
                continue

            # Execute Gemini CLI using powershell.exe
            # This is more robust on Windows for finding the 'gemini' command
            command_args = ["powershell.exe", "-NoProfile", "-Command", "gemini", "-p", content, "-y"]
            result = subprocess.run(
                command_args,
                capture_output=True,
                text=True,
                shell=False # shell=False when explicitly calling powershell.exe
            )

            log_date = datetime.now().strftime("%Y-%m-%d")
            log_path = os.path.join("Logs", f"{log_date}.md")
            with open(log_path, "a") as log_file:
                log_file.write(f"\n## {datetime.now().strftime('%H:%M:%S')} - {filename}\n")
                log_file.write(f"**Output:**\n{result.stdout}\n")
                if result.stderr:
                    log_file.write(f"**Errors:**\n{result.stderr}\n")
                log_file.write("---\n")

            # MOVE to Done: Copy first, then delete original
            done_file_path = os.path.join(done_dir, filename)
            
            # Skip if already exists in Done
            if os.path.exists(done_file_path):
                logging.warning(f"File '{filename}' already exists in Done. Removing from Needs_Action.")
                os.remove(file_path)
                if os.path.exists(meta_path):
                    os.remove(meta_path)
                continue
            
            shutil.copy2(file_path, done_file_path)

            # Verify copy success before deleting original
            if os.path.exists(done_file_path) and os.path.getsize(done_file_path) == os.path.getsize(file_path):
                logging.info(f"Successfully copied {filename} to Done")
                # Delete original from Needs_Action
                os.remove(file_path)
                logging.info(f"Removed {filename} from Needs_Action")
            else:
                logging.error(f"Copy verification failed for {filename}. Original kept in Needs_Action.")
                continue

            # Move metadata file
            if os.path.exists(meta_path):
                done_meta_path = os.path.join(done_dir, os.path.basename(meta_path))
                shutil.copy2(meta_path, done_meta_path)
                if os.path.exists(done_meta_path) and os.path.getsize(done_meta_path) == os.path.getsize(meta_path):
                    os.remove(meta_path)
                    logging.info(f"Successfully moved metadata to Done")

            processed_count += 1
            processed_file_names.append(filename)
            logging.info(f"Completed file: {filename}")

        except FileNotFoundError as e:
            if "gemini" in str(e) or "powershell" in str(e):
                logging.error(f"Error: 'powershell.exe' or 'gemini' command not found. Ensure they are in your PATH.")
            else:
                logging.error(f"File not found during processing: {e}")
        except Exception as e:
            logging.error(f"Failed to process {filename}: {e}")

    # Finalize Dashboard with processed file names and counts
    update_dashboard(processed_file_names, processed_count)


def main():
    logging.info("Orchestrator active. Watching /Needs_Action...")
    while True:
        try:
            process_needs_action()
        except KeyboardInterrupt:
            logging.info("Orchestrator stopped by user.")
            break
        except Exception as e:
            logging.error(f"Runtime error: {e}")
        time.sleep(60)

if __name__ == "__main__":
    main()
