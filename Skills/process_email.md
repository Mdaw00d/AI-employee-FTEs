# Skill: Process Email

## Name
`process_email`

## Trigger
- **File Type**: `.eml`, `.msg`, or email text files in `Needs_Action/` folder
- **File Pattern**: `Needs_Action/email_*.txt` or `Needs_Action/*.eml`

## Inputs
| Input | Description |
|-------|-------------|
| Email file | The raw email content file from `Needs_Action/` |
| `Briefings/context.md` | Optional: Current business context, ongoing conversations |
| `Approved/contacts.md` | Optional: Known contacts and their priority levels |
| `Company_Handbook.md` | Company policies for response guidelines |

## Steps
1. **Parse Email**
   - Extract sender, recipients, subject, date, body, and attachments
   - Identify if email is internal or external

2. **Classify Email**
   - Determine category: `Inquiry`, `Complaint`, `Request`, `Notification`, `Spam`, `Urgent`
   - Assess priority: `High`, `Medium`, `Low`
   - Check if sender is in approved contacts list

3. **Check Existing Context**
   - Search `Approved/` for related conversation history
   - Check if this is a reply to an existing thread
   - Look for related pending approvals

4. **Determine Action**
   - If `Spam`: Move to archive, no action needed
   - If `Notification`: File in `Done/` with summary
   - If requires response: Draft reply
   - If requires approval: Create approval request

5. **Draft Reply** (if needed)
   - Use company tone from `Company_Handbook.md`
   - Address all questions/concerns from email
   - Include relevant attachments or references
   - Add appropriate signature

6. **Create Output Files**
   - Save classification and summary to `Briefings/email_log.md`
   - If reply drafted: Save to `Pending_Approval/email_reply_<id>.md`
   - If action required: Create task in `Needs_Action/tasks.md`

## Outputs
| Output | Location | Description |
|--------|----------|-------------|
| Classification | `Briefings/email_log.md` | Email summary with category, priority, sender |
| Draft Reply | `Pending_Approval/email_reply_<id>.md` | Ready-to-send reply awaiting approval |
| Task | `Needs_Action/tasks.md` | Follow-up tasks if action required |
| Filed Email | `Done/email_<id>.md` | Processed email record with actions taken |

## Example Output: Pending_Approval/email_reply_001.md
```markdown
# Email Reply Approval

**Original Email**: Needs_Action/email_001.txt
**Sender**: client@example.com
**Subject**: Product Inquiry

## Classification
- Category: Inquiry
- Priority: Medium
- Response Required: Yes

## Draft Reply

Dear [Client],

Thank you for your inquiry about our products...

[Full reply content]

Best regards,
[Signature]

---
**Status**: Pending Approval
**Created**: 2026-03-04
```
