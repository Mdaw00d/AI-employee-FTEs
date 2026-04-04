# Skill: Summarize Social Media

## Name
`summarize_social`

## Trigger
- **Schedule**: Weekly (every Monday 6:00 AM) or on-demand
- **Manual Trigger**: File `Needs_Action/summarize_social.md` created
- **Platforms**: Facebook, Instagram, X (Twitter), LinkedIn

## Inputs
| Input | Description |
|-------|-------------|
| Platform APIs | Facebook Graph API, Instagram Basic Display, X API v2, LinkedIn API |
| `Briefings/previous_summaries/` | Historical summaries for trend comparison |
| `Briefings/Business_Goals.md` | Goals to measure social performance against |
| `Approved/social_kpis.md` | Target metrics, benchmarks, KPI definitions |

## Steps
1. **Authenticate & Connect**
   - Use stored credentials for each platform
   - Verify API access tokens are valid
   - Handle rate limiting appropriately

2. **Fetch Recent Posts** (last 7 days)
   - Retrieve all published posts per platform
   - Collect engagement metrics: likes, comments, shares, clicks, impressions
   - Download top-performing post content for analysis

3. **Fetch Audience Metrics**
   - Follower count changes
   - Demographic shifts
   - Growth rate calculations

4. **Analyze Performance**
   - Calculate engagement rate per post and platform
   - Identify top 3 and bottom 3 performing posts
   - Compare against previous week and KPIs
   - Note viral content or anomalies

5. **Sentiment Analysis**
   - Analyze comment sentiment (positive/neutral/negative)
   - Flag any concerning comments or PR issues
   - Identify common themes in audience feedback

6. **Generate Summary Report**
   - Executive summary with key highlights
   - Platform-by-platform breakdown
   - Visual-ready data tables
   - Recommendations for improvement

7. **Write Summary File**
   - Format for CEO/executive consumption
   - Include actionable insights
   - Link to detailed metrics if available

## Outputs
| Output | Location | Description |
|--------|----------|-------------|
| Weekly Summary | `Briefings/social_summary.md` | Consolidated social media performance report |
| Metrics Archive | `Briefings/previous_summaries/social_YYYY-WW.md` | Archived weekly summary |
| Alerts | `Needs_Action/social_alerts.md` | Any urgent issues requiring attention |

## Example Output: Briefings/social_summary.md
```markdown
# Social Media Weekly Summary

**Week**: 2026-W09 (Feb 24 - Mar 2, 2026)
**Generated**: 2026-03-03 06:15 AM

---

## Executive Summary

This week saw a **12% increase** in total engagement across all platforms, driven primarily by our Q1 launch announcement on LinkedIn. Instagram follower growth exceeded targets by 8%.

**Key Highlight**: LinkedIn post on product innovation reached 45K impressions (3x average).

---

## Platform Breakdown

### LinkedIn
| Metric | This Week | Last Week | Change |
|--------|-----------|-----------|--------|
| Posts Published | 5 | 4 | +1 |
| Total Impressions | 67,500 | 45,200 | +49% |
| Engagement Rate | 4.2% | 3.1% | +1.1% |
| New Followers | 234 | 189 | +45 |

**Top Post**: "Introducing Our Q1 Innovation..." (45K impressions, 892 engagements)

### Instagram
| Metric | This Week | Last Week | Change |
|--------|-----------|-----------|--------|
| Posts Published | 7 | 6 | +1 |
| Reach | 23,400 | 21,100 | +11% |
| Engagement Rate | 5.8% | 5.2% | +0.6% |
| New Followers | 456 | 398 | +58 |

### Facebook
| Metric | This Week | Last Week | Change |
|--------|-----------|-----------|--------|
| Posts Published | 4 | 4 | 0 |
| Reach | 12,300 | 13,100 | -6% |
| Engagement Rate | 2.1% | 2.3% | -0.2% |

### X (Twitter)
| Metric | This Week | Last Week | Change |
|--------|-----------|-----------|--------|
| Tweets | 12 | 10 | +2 |
| Impressions | 34,200 | 28,900 | +18% |
| Engagement Rate | 1.8% | 1.6% | +0.2% |

---

## Sentiment Analysis

- **Positive**: 78% of comments (↑ 5% from last week)
- **Neutral**: 18% of comments
- **Negative**: 4% of comments (mostly product availability questions)

**Action Item**: Respond to availability questions with timeline update.

---

## Recommendations

1. **Double down on LinkedIn** - Highest ROI platform this week
2. **Review Facebook strategy** - Slight decline in engagement
3. **Post more product visuals** - Image posts outperformed text 2:1
4. **Respond to comments within 4hrs** - Engagement correlation identified

---

## KPI Progress

| KPI | Target | Current | Status |
|-----|--------|---------|--------|
| Total Followers | 50,000 | 47,234 | 🟡 On Track |
| Avg Engagement Rate | 4.0% | 4.1% | 🟢 Achieved |
| Weekly Growth | 2% | 2.4% | 🟢 Achieved |

---

**Next Summary**: 2026-03-10 06:00 AM
```
