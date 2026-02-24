import os
from datetime import datetime

def update_dashboard_only():
    """Update Dashboard.md with correct pending task count only"""
    dashboard_path = "./Dashboard.md"

    # Read current dashboard content
    if os.path.exists(dashboard_path):
        with open(dashboard_path, 'r') as f:
            content = f.read()
    else:
        # Create basic dashboard if it doesn't exist
        content = """# Dashboard

## System Status
System operational

## Pending Tasks Count
[PLACEHOLDER]

## Recent Activity
[Recent activity will be logged here]
"""

    # Calculate pending tasks count (files in Needs_Action excluding metadata)
    needs_action_dir = "./Needs_Action"
    pending_count = 0
    if os.path.exists(needs_action_dir):
        pending_files = [f for f in os.listdir(needs_action_dir)
                        if os.path.isfile(os.path.join(needs_action_dir, f)) and not f.endswith('_metadata.md')]
        pending_count = len(pending_files)

    # Update pending tasks count
    content = content.replace("## Pending Tasks Count\n[PLACEHOLDER]",
                             f"## Pending Tasks Count\n{pending_count}")

    # If placeholder doesn't exist, find the right place to insert the count
    if f"## Pending Tasks Count\n{pending_count}" not in content:
        content = content.replace("## Pending Tasks Count\n[PLACEHOLDER]",
                                 f"## Pending Tasks Count\n{pending_count}")
        if f"## Pending Tasks Count\n{pending_count}" not in content:
            # If we can't find the exact placeholder pattern, just update the number
            import re
            content = re.sub(r'(## Pending Tasks Count\s*\n)\d+', r'\g<1>' + str(pending_count), content)

    # Write updated content back to dashboard
    with open(dashboard_path, 'w') as f:
        f.write(content)

    print(f"Updated Dashboard.md with correct pending task count: {pending_count}")

if __name__ == "__main__":
    update_dashboard_only()
    print("Dashboard update complete!")