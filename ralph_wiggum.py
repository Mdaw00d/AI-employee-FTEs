#!/usr/bin/env python3
"""
Ralph Wiggum - Gold Tier Loop Controller
=========================================
Implements iterative AI task processing for complex multi-step tasks.
Loops until <TASK_COMPLETE> marker is found in Qwen response or file appears in Done/.

Usage:
    python ralph_wiggum.py --task "path/to/task.md"           # Process single task with loop
    python ralph_wiggum.py --task "path/to/task.md" --max-iterations 15
    python ralph_wiggum.py --orchestrator-loop                # Enable loop mode in orchestrator

Environment Variables:
    QWEN_API_URL      - URL to Qwen API endpoint (optional)
    OPENAI_API_BASE   - Alternative API endpoint (optional)
    OPENAI_API_KEY    - API key for AI calls (optional)
"""

import os
import sys
import shutil
import time
import logging
import argparse
import subprocess
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# ============================================================================
# Configuration
# ============================================================================

LOGS_DIR = "./Logs"
NEEDS_ACTION_DIR = "./Needs_Action"
DONE_DIR = "./Done"
PLANS_DIR = "./Plans"
PENDING_APPROVAL_DIR = "./Pending_Approval"
APPROVED_DIR = "./Approved"
DASHBOARD_FILE = "./Dashboard.md"
COMPANY_HANDBOOK_FILE = "./Company_Handbook.md"

RALPH_LOG_FILE = os.path.join(LOGS_DIR, "ralph_loop.log")

DEFAULT_MAX_ITERATIONS = 10
CONTINUATION_PROMPT = "\n\nContinue until complete. Write <TASK_COMPLETE> when finished.\n"

TASK_COMPLETE_MARKER = "<TASK_COMPLETE>"

# Ensure directories exist
os.makedirs(LOGS_DIR, exist_ok=True)

# Configure Ralph-specific logging
ralph_logger = logging.getLogger("ralph_wiggum")
ralph_logger.setLevel(logging.INFO)

# File handler for Ralph log
file_handler = logging.FileHandler(RALPH_LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'
))

ralph_logger.addHandler(file_handler)
ralph_logger.addHandler(console_handler)


# ============================================================================
# Ralph Wiggum Loop Controller
# ============================================================================

class RalphWiggumController:
    """
    Controls iterative AI task processing loop.
    
    Named after Chief Ralph Wiggum - "I'm not usually a detective, but I play one on TV."
    This controller keeps asking the AI until the task is actually complete.
    """
    
    def __init__(self, max_iterations: int = DEFAULT_MAX_ITERATIONS):
        self.max_iterations = max_iterations
        self.current_iteration = 0
        self.task_complete = False
        self.iteration_history: List[Dict] = []
        
    def log_iteration(self, iteration: int, status: str, details: str):
        """Log iteration details to Ralph log."""
        ralph_logger.info(f"[Iteration {iteration}/{self.max_iterations}] {status}: {details}")
        self.iteration_history.append({
            'iteration': iteration,
            'status': status,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
    
    def check_task_complete_in_response(self, response: str) -> bool:
        """Check if response contains task complete marker."""
        return TASK_COMPLETE_MARKER in response
    
    def check_task_complete_in_done(self, original_filename: str) -> bool:
        """Check if task file has been moved to Done/."""
        done_path = os.path.join(DONE_DIR, original_filename)
        return os.path.exists(done_path)
    
    def check_approval_pending(self) -> bool:
        """Check if there are pending approval files."""
        if not os.path.exists(PENDING_APPROVAL_DIR):
            return False
        files = [f for f in os.listdir(PENDING_APPROVAL_DIR) 
                 if f.endswith('.md') and not f.startswith('.')]
        return len(files) > 0
    
    def get_pending_approvals(self) -> List[str]:
        """Get list of pending approval files."""
        if not os.path.exists(PENDING_APPROVAL_DIR):
            return []
        return [f for f in os.listdir(PENDING_APPROVAL_DIR) 
                if f.endswith('.md') and not f.startswith('.')]
    
    def run_loop(self, task_file_path: str, process_callback) -> Tuple[bool, int]:
        """
        Run the Ralph Wiggum loop for a task.
        
        Args:
            task_file_path: Path to the task file in Needs_Action/
            process_callback: Function to call for each iteration.
                              Should return (response_text, files_created)
        
        Returns:
            Tuple of (success: bool, iterations_used: int)
        """
        filename = os.path.basename(task_file_path)
        ralph_logger.info("=" * 60)
        ralph_logger.info(f"RALPH WIGGUM LOOP STARTED for: {filename}")
        ralph_logger.info(f"Max iterations: {self.max_iterations}")
        ralph_logger.info("=" * 60)
        
        accumulated_context = ""
        last_response = ""
        
        for self.current_iteration in range(1, self.max_iterations + 1):
            ralph_logger.info(f"\n{'='*40}")
            ralph_logger.info(f"ITERATION {self.current_iteration}/{self.max_iterations}")
            ralph_logger.info(f"{'='*40}")
            
            # Build context for this iteration
            iteration_context = self._build_iteration_context(
                filename, 
                accumulated_context, 
                last_response
            )
            
            # Call the process callback
            try:
                response, files_created = process_callback(iteration_context, self.current_iteration)
                last_response = response
                self.iteration_history[-1]['files_created'] = files_created
            except Exception as e:
                ralph_logger.error(f"Iteration {self.current_iteration} failed: {e}")
                self.log_iteration(self.current_iteration, "ERROR", str(e))
                continue
            
            # Check for task completion in response
            if self.check_task_complete_in_response(response):
                ralph_logger.info(f"Task complete marker found in response!")
                self.log_iteration(self.current_iteration, "COMPLETE", "Marker found in response")
                self.task_complete = True
                break
            
            # Check if file moved to Done/
            if self.check_task_complete_in_done(filename):
                ralph_logger.info(f"Task file moved to Done/!")
                self.log_iteration(self.current_iteration, "COMPLETE", "File in Done/")
                self.task_complete = True
                break
            
            # Accumulate context for next iteration
            accumulated_context += f"\n\n--- Iteration {self.current_iteration} Output ---\n{response}\n"
            
            # Check if we need human approval
            if self.check_approval_pending():
                approvals = self.get_pending_approvals()
                ralph_logger.info(f"Waiting for human approval: {approvals}")
                self.log_iteration(self.current_iteration, "WAITING_APPROVAL", str(approvals))
                # Don't break - continue loop after approval might be needed
                # but give time for human to respond
                time.sleep(2)
            
            ralph_logger.info(f"Task not complete, continuing to next iteration...")
            self.log_iteration(self.current_iteration, "CONTINUING", "No completion marker yet")
        
        # Final status
        if self.task_complete:
            ralph_logger.info("=" * 60)
            ralph_logger.info(f"RALPH WIGGUM LOOP COMPLETED SUCCESSFULLY")
            ralph_logger.info(f"Total iterations: {self.current_iteration}")
            ralph_logger.info("=" * 60)
            return True, self.current_iteration
        else:
            ralph_logger.warning("=" * 60)
            ralph_logger.warning(f"RALPH WIGGUM LOOP REACHED MAX ITERATIONS")
            ralph_logger.warning(f"Task may not be fully complete!")
            ralph_logger.warning("=" * 60)
            return False, self.max_iterations
    
    def _build_iteration_context(self, filename: str, accumulated: str, last_response: str) -> str:
        """Build context string for the current iteration."""
        context_parts = []
        
        # Original task indicator
        context_parts.append(f"Original Task: {filename}")
        
        # Add accumulated context from previous iterations
        if accumulated:
            context_parts.append(f"\nPrevious Iterations Summary:")
            context_parts.append(accumulated)
        
        # Add continuation instruction
        if self.current_iteration > 1:
            context_parts.append(CONTINUATION_PROMPT)
        
        return "\n".join(context_parts)
    
    def get_summary(self) -> str:
        """Get a summary of the loop execution."""
        summary_lines = [
            f"Ralph Wiggum Loop Summary",
            f"=========================",
            f"Max Iterations: {self.max_iterations}",
            f"Iterations Used: {self.current_iteration}",
            f"Task Complete: {self.task_complete}",
            f"",
            f"Iteration History:",
        ]
        
        for entry in self.iteration_history:
            summary_lines.append(
                f"  [{entry['iteration']}] {entry['status']}: {entry['details'][:50]}..."
            )
        
        return "\n".join(summary_lines)


# ============================================================================
# Integration with Orchestrator
# ============================================================================

def call_qwen_api(prompt: str, context: str = "") -> str:
    """
    Call Qwen API (or compatible OpenAI endpoint) for task processing.
    
    Args:
        prompt: The main prompt to send
        context: Additional context from previous iterations
    
    Returns:
        AI response text
    """
    api_url = os.getenv("QWEN_API_URL", os.getenv("OPENAI_API_BASE", ""))
    api_key = os.getenv("OPENAI_API_KEY", "")
    
    # If no API configured, return placeholder for testing
    if not api_url:
        ralph_logger.warning("No API URL configured. Using mock response for testing.")
        return f"Mock response for iteration. {TASK_COMPLETE_MARKER}"
    
    # Build the request
    messages = [
        {"role": "system", "content": "You are an autonomous AI Employee."},
        {"role": "user", "content": context + "\n\n" + prompt if context else prompt}
    ]
    
    request_data = {
        "model": "qwen-plus",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4096
    }
    
    try:
        import urllib.request
        import urllib.error
        
        data = json.dumps(request_data).encode('utf-8')
        req = urllib.request.Request(
            api_url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}' if api_key else ''
            }
        )
        
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('choices', [{}])[0].get('message', {}).get('content', '')
    
    except Exception as e:
        ralph_logger.error(f"API call failed: {e}")
        raise


def process_with_loop(task_file_path: str, max_iterations: int = DEFAULT_MAX_ITERATIONS) -> Tuple[bool, int]:
    """
    Process a task file using the Ralph Wiggum loop.
    
    Args:
        task_file_path: Path to task file in Needs_Action/
        max_iterations: Maximum number of iterations
    
    Returns:
        Tuple of (success: bool, iterations_used: int)
    """
    filename = os.path.basename(task_file_path)
    
    # Read original task content
    try:
        with open(task_file_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        ralph_logger.error(f"Failed to read task file: {e}")
        return False, 0
    
    # Load handbook if available
    handbook_content = ""
    if os.path.exists(COMPANY_HANDBOOK_FILE):
        with open(COMPANY_HANDBOOK_FILE, 'r', encoding='utf-8') as f:
            handbook_content = f.read()
    
    # Create controller
    controller = RalphWiggumController(max_iterations=max_iterations)
    
    # Define the process callback
    def process_callback(iteration_context: str, iteration_num: int) -> Tuple[str, List[str]]:
        """Callback for each iteration - calls AI and processes response."""
        
        # Build full prompt
        full_prompt = f"""
================================================================================
AI EMPLOYEE TASK PROCESSING - ITERATION {iteration_num}
================================================================================

You are an autonomous AI Employee working for this organization.

## Your Role
- Process tasks assigned to you in a professional and concise manner
- Think step-by-step before taking action
- Follow all company rules and guidelines

{iteration_context}

================================================================================
ORIGINAL TASK CONTENT
================================================================================

**Task File:** {filename}
**Received:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

{original_content}

================================================================================
INSTRUCTIONS
================================================================================

1. Read the task content carefully
2. Review any previous iteration outputs above
3. Continue working on the task step-by-step
4. If multi-step, create Plan_*.md in Plans/ directory
5. If action requires approval, create Pending_Approval/*.md
6. When the ENTIRE task is finished:
   - Move original file to Done/
   - Append completion to Dashboard.md
   - Write {TASK_COMPLETE_MARKER} at the end of your response

If this is a continuation (iteration > 1), continue from where you left off.
Do not repeat work already done in previous iterations.

================================================================================
BEGIN YOUR RESPONSE
================================================================================
"""
        
        # Call AI (this would integrate with your actual AI system)
        # For now, we'll simulate by calling orchestrator's process function
        response = call_qwen_api(full_prompt, handbook_content)
        
        # Track files created (simplified - in reality you'd parse the response)
        files_created = []
        
        return response, files_created
    
    # Run the loop
    success, iterations = controller.run_loop(task_file_path, process_callback)
    
    # Log summary
    ralph_logger.info(controller.get_summary())
    
    return success, iterations


# ============================================================================
# Orchestrator Integration Mode
# ============================================================================

def enable_orchestrator_loop_mode():
    """
    Patch the orchestrator to use Ralph Wiggum loop mode.
    
    This function modifies orchestrator behavior to loop Qwen calls
    for complex tasks until completion.
    """
    ralph_logger.info("Enabling Ralph Wiggum loop mode for orchestrator")
    
    # Import orchestrator functions
    try:
        import orchestrator
    except ImportError:
        ralph_logger.error("Could not import orchestrator module")
        return False
    
    # Store original process function
    original_process = orchestrator.process_task_file
    
    def looped_process_task_file(file_path: str, handbook_content: str = "") -> bool:
        """Wrapped process that uses Ralph Wiggum loop."""
        filename = os.path.basename(file_path)
        
        ralph_logger.info(f"Ralph Wiggum mode: Processing {filename} with loop")
        
        # Use Ralph loop
        success, iterations = process_with_loop(file_path, max_iterations=DEFAULT_MAX_ITERATIONS)
        
        if success:
            ralph_logger.info(f"Ralph Wiggum loop completed for {filename} in {iterations} iterations")
        else:
            ralph_logger.warning(f"Ralph Wiggum loop reached max iterations for {filename}")
        
        return success
    
    # Replace the orchestrator's process function
    orchestrator.process_task_file = looped_process_task_file
    
    ralph_logger.info("Orchestrator patched with Ralph Wiggum loop mode")
    return True


def run_orchestrator_with_loop(max_iterations: int = DEFAULT_MAX_ITERATIONS):
    """
    Run orchestrator with Ralph Wiggum loop enabled.
    
    This is an alternative entry point that starts orchestrator
    with loop mode automatically enabled.
    """
    ralph_logger.info("=" * 60)
    ralph_logger.info("Starting Orchestrator with Ralph Wiggum Loop Mode")
    ralph_logger.info(f"Max iterations per task: {max_iterations}")
    ralph_logger.info("=" * 60)
    
    # Enable loop mode
    if not enable_orchestrator_loop_mode():
        ralph_logger.error("Failed to enable loop mode, falling back to normal mode")
        # Fall back to normal orchestrator
        subprocess.run([sys.executable, "orchestrator.py"])
        return
    
    # Now run orchestrator (it will use the patched function)
    try:
        import orchestrator
        orchestrator.main()
    except Exception as e:
        ralph_logger.error(f"Orchestrator failed: {e}")
        raise


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Main entry point for Ralph Wiggum."""
    parser = argparse.ArgumentParser(
        description='Ralph Wiggum - Gold Tier Loop Controller',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single task with loop
  python ralph_wiggum.py --task Needs_Action/task_001.md
  
  # Process with custom max iterations
  python ralph_wiggum.py --task Needs_Action/task_001.md --max-iterations 15
  
  # Run orchestrator with loop mode enabled
  python ralph_wiggum.py --orchestrator-loop
  
  # Run orchestrator with loop mode and custom iterations
  python ralph_wiggum.py --orchestrator-loop --max-iterations 15
        """
    )
    
    parser.add_argument(
        '--task',
        type=str,
        help='Path to task file to process with loop'
    )
    
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=DEFAULT_MAX_ITERATIONS,
        help=f'Maximum iterations (default: {DEFAULT_MAX_ITERATIONS})'
    )
    
    parser.add_argument(
        '--orchestrator-loop',
        action='store_true',
        help='Run orchestrator with Ralph Wiggum loop mode enabled'
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run a test loop to verify configuration'
    )
    
    args = parser.parse_args()
    
    # Test mode
    if args.test:
        ralph_logger.info("Running Ralph Wiggum test...")
        ralph_logger.info(f"Log file: {RALPH_LOG_FILE}")
        ralph_logger.info(f"Max iterations: {args.max_iterations}")
        
        # Test the controller
        controller = RalphWiggumController(max_iterations=args.max_iterations)
        controller.log_iteration(1, "TEST", "Test iteration logged successfully")
        
        ralph_logger.info("Test complete! Check Logs/ralph_loop.log for results.")
        return
    
    # Orchestrator loop mode
    if args.orchestrator_loop:
        run_orchestrator_with_loop(max_iterations=args.max_iterations)
        return
    
    # Single task processing
    if args.task:
        if not os.path.exists(args.task):
            ralph_logger.error(f"Task file not found: {args.task}")
            sys.exit(1)
        
        ralph_logger.info(f"Processing task with Ralph Wiggum loop: {args.task}")
        success, iterations = process_with_loop(args.task, max_iterations=args.max_iterations)
        
        if success:
            ralph_logger.info(f"Task completed successfully in {iterations} iterations")
            sys.exit(0)
        else:
            ralph_logger.warning(f"Task may be incomplete after {iterations} iterations")
            sys.exit(1)
    
    # No arguments - show help
    parser.print_help()


if __name__ == "__main__":
    main()
