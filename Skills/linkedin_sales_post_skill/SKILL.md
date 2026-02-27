---
name: linkedin-sales-post-skill
description: Generate engaging LinkedIn sales posts from business goals and completed work, then submit for human approval before publishing.
---

# LinkedIn Sales Post Skill

This skill creates engaging LinkedIn posts based on business objectives and recent accomplishments, then submits them for human approval before publishing.

## Inputs

1. **Business_Goals.md** (required)
   - Located in root directory
   - Contains target audience, value propositions, and messaging guidelines

2. **Done/ directory** (optional)
   - Recent completed task files
   - Used to extract wins, testimonials, and accomplishments

## Output Format

Generates LinkedIn posts with the following structure:

```
[Hook - attention grabbing opening]

[Value - key message or benefit]

[CTA - clear call to action]

[3-5 relevant hashtags]
```

**Character Limit:** 200-350 characters (excluding hashtags)

## Workflow

### Step 1: Read Inputs
- Load `Business_Goals.md` for messaging guidelines
- Scan `Done/` directory for recent accomplishments (last 7 days)
- Extract key wins, client feedback, or completed projects

### Step 2: Generate Post
Create engaging post text following this structure:

| Element | Purpose | Example |
|---------|---------|---------|
| **Hook** | Grab attention in first line | "Just helped a client save 20hrs/week" |
| **Value** | Show benefit or result | "Automation isn't about replacing people—it's about freeing them for meaningful work." |
| **CTA** | Drive engagement | "What's your biggest time-waster? Drop it below 👇" |
| **Hashtags** | Increase reach (3-5) | #Automation #Productivity #BusinessGrowth |

### Step 3: Write Draft
Save full draft to `Plans/LinkedIn_Draft_{YYYYMMDD_HHMMSS}.md`:

```markdown
---
type: linkedin_draft
created: {timestamp}
character_count: {count}
source_files: [list of source files used]
---

# LinkedIn Post Draft

{post_text}

---
## Generation Notes
- Hook type: {type}
- CTA type: {type}
- Hashtags: {list}
```

### Step 4: Create Approval Request
Create `Pending_Approval/LINKEDIN_POST_{hash}.md`:

```markdown
---
type: approval_request
action: post_linkedin
draft_file: Plans/LinkedIn_Draft_{date}.md
post_text: |
  {full post text}
character_count: {count}
created: {timestamp}
status: pending
---

# LinkedIn Post Approval Request

## Post Preview

{post_text}

## Instructions

**To Approve:** Move this file to `Approved/` directory → Post will be published automatically

**To Reject:** Move this file to `Rejected/` directory → Post will be discarded

**To Edit:** Move to `Plans/`, edit the `post_text` field, then move back to `Pending_Approval/`

---

## Metadata
- Draft: `{draft_file}`
- Character Count: {count}
- Created: {timestamp}
```

## Guidelines

### Tone (from Company_Handbook.md)
- **Professional** - Maintain business credibility
- **Concise** - Every word must earn its place

### Best Practices
- Lead with results, not features
- Use numbers/social proof when possible
- Ask questions to drive engagement
- Avoid overly salesy language
- Include 1 emoji max (optional)

### Hashtag Strategy
- 1 broad: #Business #Marketing #Sales
- 2-3 niche: #B2BSales #LeadGeneration #SalesAutomation
- 1 branded (if applicable): #YourCompany

### Compliance
- Never post financial claims without approval
- Never share client names without permission
- Follow company brand guidelines

## Approval Flow

```
Pending_Approval/
       │
       ├──→ Approved/     → Auto-publish via linkedin_approval_handler.py
       │
       └──→ Rejected/     → Discard post
```

## Integration

This skill works with:
- `linkedin_approval_handler.py` - Publishes approved posts
- `orchestrator.py` - Can trigger post generation as a task
