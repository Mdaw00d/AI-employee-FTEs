---
name: process-task
description: Process all pending tasks in the /Needs_Action directory and move them to /Done.
---

# Process Task Skill

This skill provides the workflow for processing files that have been placed in the `/Needs_Action` directory.

## Workflow

For each file in the `/Needs_Action` directory:

1. **Process Task:** Perform any necessary operations on the file content based on its content and metadata.
2. **Move to /Done:** Once the task is completed, move the file (and its associated metadata file, if any) from `/Needs_Action` to the `/Done` directory.
3. **Update Dashboard.md:**
   - **Recent Activity:** Add a new entry under the "## Recent Activity" section with the current timestamp and the name of the processed file.
   - **Pending Task Count:** Update the number under the "## Pending Tasks Count" section to accurately reflect the remaining files in the `/Needs_Action` directory.

## Guidelines
- Follow the instructions in the file content or metadata if they exist.
- Ensure the Dashboard.md is updated for every single file processed.
- If `/Needs_Action` is empty, no action is needed.
