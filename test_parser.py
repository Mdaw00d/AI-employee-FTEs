#!/usr/bin/env python3
"""Test the post content extraction."""

import re

def parse_post_content(file_path):
    """Parse a scheduled post file and extract content."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract frontmatter
    frontmatter_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not frontmatter_match:
        return None
    
    frontmatter = frontmatter_match.group(1)
    
    # Extract post content - handle both inline and multiline formats
    # Find post_content line and capture everything until the next YAML key or end of frontmatter
    lines = frontmatter.split('\n')
    post_content_lines = []
    in_post_content = False
    
    for i, line in enumerate(lines):
        if line.startswith('post_content:'):
            # Get content after the colon on the same line
            after_colon = line.split(':', 1)[1].strip()
            if after_colon:
                post_content_lines.append(after_colon)
            in_post_content = True
        elif in_post_content:
            # Check if this is a new YAML key (word at start followed by colon)
            if re.match(r'^\w+:', line):
                # New YAML key found, stop collecting
                break
            else:
                # This is a continuation line (including empty lines)
                post_content_lines.append(line)
    
    return '\n'.join(post_content_lines).strip() if post_content_lines else None

# Test with the LinkedIn post
test_files = [
    'Scheduled_Posts/LINKEDIN_POST_TODAY_20260329_1800.md',
    'Scheduled_Posts/FACEBOOK_POST_20260330_1800.md',
    'Scheduled_Posts/X_POST_20260401_1200.md',
]

for test_file in test_files:
    print(f"\n{'='*60}")
    print(f"Testing: {test_file}")
    print('='*60)
    result = parse_post_content(test_file)
    if result:
        print(f"Content length: {len(result)} chars")
        print(f"First 200 chars:\n{result[:200]}")
    else:
        print("FAILED: No content extracted")
    
    # Debug: show frontmatter lines
    print("\n--- Frontmatter lines ---")
    with open(test_file, 'r', encoding='utf-8') as f:
        content = f.read()
    frontmatter_match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)
        lines = frontmatter.split('\n')
        for i, line in enumerate(lines):
            print(f'{i}: {repr(line)}')
