# Skill: Weekly Audit

## Name
`weekly_audit`

## Trigger
- **Schedule**: Every Friday at 4:00 PM (end of business week)
- **Manual Trigger**: `Needs_Action/run_weekly_audit.md` created
- **Post-Processing**: After all daily tasks are moved to `Done/`

## Inputs
| Input | Description |
|-------|-------------|
| `Accounting/` | All accounting records, invoices, transactions for the week |
| `Done/` | Completed tasks, processed emails, social posts from the week |
| `Briefings/` | All briefings, summaries, logs generated during the week |
| `Pending_Approval/` | Items still awaiting approval (carry-over) |
| `Briefings/Business_Goals.md` | Goals to measure weekly progress against |
| `Company_Handbook.md` | Company policies for compliance checking |

## Steps
1. **Collect Weekly Data**
   - Scan `Accounting/` for all transactions (date-filtered)
   - Scan `Done/` for all completed items
   - Scan `Briefings/` for all summaries and logs
   - Count items in `Pending_Approval/` (aging report)

2. **Accounting Summary**
   - Total invoices created
   - Total payments processed
   - Outstanding receivables/payables
   - Revenue summary (if accessible)
   - Flag any accounting anomalies

3. **Task Completion Analysis**
   - Count tasks completed per category (email, social, accounting)
   - Calculate completion rate vs. tasks created
   - Identify bottlenecks or recurring task types
   - Note any SLA breaches or delays

4. **Social Media Summary**
   - Aggregate daily social summaries
   - Week-over-week engagement comparison
   - Content performance highlights
   - Follower growth summary

5. **Approval Queue Health**
   - Count pending items by age (<24hrs, 24-48hrs, >48hrs)
   - Identify stale approvals needing escalation
   - Flag any critical items pending too long

6. **Goal Progress Check**
   - Compare weekly outputs against `Business_Goals.md` KPIs
   - Calculate progress percentage for quarterly goals
   - Identify goals at risk or ahead of schedule

7. **Generate CEO Briefing**
   - Executive summary (3-5 key points)
   - Financial snapshot
   - Operational highlights
   - Risks and concerns
   - Next week priorities
   - Decisions required from CEO

8. **Archive Week's Data**
   - Move processed files to weekly archive
   - Update master logs
   - Clean up temporary files

## Outputs
| Output | Location | Description |
|--------|----------|-------------|
| CEO Briefing | `Briefings/ceo_briefing_week_YYYY_WW.md` | Executive weekly summary |
| Audit Report | `Briefings/weekly_audit_YYYY_WW.md` | Detailed operational audit |
| Carry-Over List | `Needs_Action/carryover_week_YYYY_WW.md` | Pending items for next week |
| Archive | `Archive/week_YYYY_WW/` | Archived week's processed files |

## Example Output: Briefings/ceo_briefing_week_2026_09.md
```markdown
# CEO Weekly Briefing

**Week**: 2026-W09 (February 24 - March 2, 2026)
**Generated**: 2026-03-02 4:30 PM
**Prepared By**: AI Operations Assistant

---

## Executive Summary

1. **Revenue Operations**: 47 invoices generated totaling $127,450; 98% collection rate on receivables
2. **Customer Engagement**: Social media reach up 34% week-over-week; LinkedIn driving 60% of engagement
3. **Operational Efficiency**: 234 tasks completed (94% completion rate); 8 items pending approval
4. **Key Win**: Q1 product launch campaign exceeded engagement targets by 45%

---

## Financial Snapshot

| Metric | This Week | Last Week | MTD |
|--------|-----------|-----------|-----|
| Invoices Issued | 47 | 42 | 89 |
| Total Value | $127,450 | $118,200 | $245,650 |
| Payments Received | $124,800 | $115,000 | $239,800 |
| Outstanding AR | $45,200 | $52,100 | - |
| Collection Rate | 98% | 97% | 97.5% |

**Note**: Outstanding AR decreased 13% - improved collections effort showing results.

---

## Operational Highlights

### Task Completion
| Category | Completed | Pending | Success Rate |
|----------|-----------|---------|--------------|
| Email Processing | 89 | 3 | 97% |
| Social Media | 28 posts | 2 drafts | 93% |
| Accounting | 52 transactions | 1 approval | 98% |
| Customer Support | 65 tickets | 0 | 100% |
| **Total** | **234** | **6** | **94%** |

### Social Media Performance
- **Total Reach**: 142,300 (↑ 34% from last week)
- **Engagement Rate**: 4.1% (↑ 0.3%)
- **New Followers**: 1,247 across all platforms
- **Top Content**: Q1 Launch announcement (45K LinkedIn impressions)

---

## Approval Queue Status

| Age | Count | Priority Items |
|-----|-------|----------------|
| < 24 hours | 4 | 0 |
| 24-48 hours | 2 | 1 (vendor payment $25K) |
| > 48 hours | 2 | 1 (partnership agreement) |

**⚠️ Action Required**: 2 items pending >48hrs need your attention.

---

## Goal Progress (Q1 2026)

| Goal | Target | Current | Progress |
|------|--------|---------|----------|
| Revenue | $2.5M | $687K | 27.5% 🟢 On Track |
| Customer Acquisition | 500 | 142 | 28.4% 🟢 On Track |
| Social Following | 50K | 47.2K | 94.4% 🟢 Ahead |
| Product Launch | 3 features | 2 launched | 67% 🟡 Slight Delay |

---

## Risks & Concerns

1. **Product Launch Delay**: Feature #3 delayed by 1 week due to QA findings
   - **Mitigation**: Extended testing window; new launch date March 12
   - **Impact**: Minimal - marketing timeline adjusted

2. **Vendor Payment Pending**: $25K payment awaiting approval (2 days)
   - **Risk**: Late fee potential if not approved by March 5
   - **Action**: Requires your approval in Pending_Approval/

---

## Next Week Priorities

1. Complete Q1 product launch (Feature #3 go-live)
2. Close 3 enterprise deals in pipeline ($180K value)
3. Approve vendor payments to maintain relationships
4. Review Q2 planning documents (draft ready)

---

## Decisions Required

| Decision | Context | Deadline |
|----------|---------|----------|
| Vendor payment approval | $25K - Enterprise Solutions Ltd | Mar 5 |
| Partnership agreement sign-off | TechPartners Inc. collaboration | Mar 7 |
| Q2 budget preliminary review | Draft available in Briefings/ | Mar 10 |

---

## Appendix

- **Detailed Audit**: Briefings/weekly_audit_2026_09.md
- **Social Summary**: Briefings/social_summary.md (Week 09)
- **Accounting Report**: Accounting/weekly_summary_2026_09.md
- **Pending Approvals**: Pending_Approval/ (8 items)

---

**Next Briefing**: 2026-03-09 4:00 PM (Week 10)
```
