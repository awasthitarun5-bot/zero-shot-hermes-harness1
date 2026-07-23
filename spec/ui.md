# UI Specification — UP Police Data Analyst

## Layout

Single-page application. No login screen in Phase 1.

```
┌──────────────────────────────────────────────────────────────────┐
│  🛡 UP Police Data Analyst              [DB: Connected ✓]        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Ask a question about your data...                    [▶] │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Step 1/5 ████░░░░░░░░░░░░░░░░  Planning...                      │
│                                                                  │
│  ─────────────────────────────────────────────────────────────  │
│                                                                  │
│  Answer                                                          │
│  Lucknow district had the highest spike with 124 FIRs last      │
│  month — 27% above the district average (78).                   │
│                                                                  │
│  🔍 Generated SQL (click to expand)                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ SELECT district, COUNT(*) AS fir_count                    │   │
│  │ FROM fir_registry                                         │   │
│  │ WHERE MONTH(registered_at) = MONTH(DATEADD(m, -1, GETDATE())) │ │
│  │ GROUP BY district ORDER BY fir_count DESC                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─ Data Table (75 rows) ──────────────────────────────────┐   │
│  │ District        │ FIR Count │ vs Mean │ Severity        │   │
│  │ Lucknow         │ 124       │ +59%    │ 🔴 High         │   │
│  │ Kanpur          │ 98        │ +26%    │ 🟡 Medium       │   │
│  │ ...             │ ...       │ ...     │ ...             │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                                  │
│  📊 [Bar chart — district FIR counts, sorted descending]        │
│                                                                  │
│  [📥 Download CSV (75 rows)]    [🔄 Regenerate chart]           │
│                                                                  │
│  💡 Suggested follow-ups                                         │
│  • Want to break this down by police station?                   │
│  • Want to see the last 6-month trend for Lucknow?              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Key Elements

### Header
- App name + icon (shield/badge motif — no external assets; inline SVG or emoji)
- DB status indicator: green dot "Connected ✓" or amber "Fallback (SQLite)" or red "Unreachable"

### Question Input
- Full-width text input, `Enter` to submit, loading disabled while a query is in-flight
- Placeholder: "Ask a question about FIRs, challans, daily diary..."
- Debounce: 300 ms

### Step Progress Indicator
- 5 labelled steps: **Plan → SQL → Validate → Execute → Explain**
- Animated progress bar; current step highlighted in blue
- On error: step turns red, error message shown inline (e.g. "Validate failed: column 'xyz' not found — retrying...")

### Answer Panel
- **Text answer:** 1–3 sentences, top anomalies summarised in plain numbers with the severity badge
- **SQL reveal:** Collapsible `<details>` section. Shows the full SQL with syntax-highlighted keywords. Copy button.
- **Data table:** Sortable columns. Severity badge column. Paginated at 25 rows/page with total count shown.
- **Chart:** Bar chart (horizontal for readability of district names) rendered with Chart.js loaded from CDN *or* inline SVG fallback if CDN is blocked (intranet may not have internet). Option: simple CSS bar chart for zero-dependency rendering.
- **CSV download:** `<a>` tag with `download` attribute; constructs CSV from the in-memory row array.

### Error + Retry State
- If the agent cannot produce a valid SQL after 2 attempts:
  - Step indicator shows red on `sql_gen` and `validate`
  - Answer panel shows: "I couldn't generate a valid query for that. Could you try rephrasing or adding a location/district?"
  - Follow-up suggestions are still shown based on the last successful attempt's context
  - Audit log records the failure with the error message

### Stubs (Phase 1 — visibly non-functional)
- **"Upload CSV" button** in the header — opens a modal that shows a message: "CSV upload is coming in the next update. For now, questions run against the full operational database."
- **"Export PDF" button** next to CSV download — visible but disabled, tooltip "Coming in Phase 2"

### Mobile
- Table scrolls horizontally; chart resizes with container
- No mobile-specific layout, but no hard minimum width (works down to ~320 px)

---

## Frontend Tech

- Plain HTML + CSS + JS in `frontend/public/`
- Chart: prefer inline SVG/CSS bar chart for zero-dependency; Chart.js CDN as progressive enhancement (wrapped in try/catch)
- State: single fetch per query; DOM updated from the JSON response
- No framework, no build step
