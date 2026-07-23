# API Contract — UP Police Data Analyst

## Base URL

```
http://<host>:8001
```

## Endpoints

### GET /health
Liveness probe. Returns 200 with service status.

**Response**
```json
{
  "status": "ok",
  "db": "connected|fallback_sqlite|unreachable",
  "llm": "anthropic/claude-3-5-sonnet|unavailable"
}
```

---

### POST /api/query
Submit a natural-language question. Returns the agent's structured answer.

**Request**
```json
{
  "question": "How many FIRs were registered in each district last month?"
}
```

**Response (200, application/json)**
```json
{
  "answer": "...plain-English summary...",
  "sql": "SELECT district, COUNT(*) AS fir_count FROM fir_registry ...",
  "columns": ["district", "fir_count"],
  "rows": [
    {"district": "Lucknow", "fir_count": 124},
    {"district": "Kanpur", "fir_count": 98}
  ],
  "row_count": 75,
  "duration_ms": 3200,
  "anomalies": [
    {
      "field": "fir_count",
      "label": "Lucknow spike",
      "value": 124,
      "severity": "high"
    }
  ],
  "followups": [
    "Want me to break this down by police station?",
    "Want to see the trend over the last 6 months?"
  ],
  "steps": [
    {"name": "plan", "status": "done"},
    {"name": "sql_gen", "status": "done"},
    {"name": "validate", "status": "done"},
    {"name": "execute", "status": "done"},
    {"name": "explain", "status": "done"}
  ],
  "csv_url": "/api/download-csv?session_id=abc123",
  "error": null
}
```

**Error response (500)**
```json
{
  "answer": "Couldn't generate a valid query — try rephrasing your question.",
  "sql": null,
  "rows": [],
  "row_count": 0,
  "duration_ms": 1100,
  "anomalies": [],
  "followups": ["Try asking for a single district first..."],
  "steps": [
    {"name": "plan", "status": "done"},
    {"name": "sql_gen", "status": "error"},
    ...
  ],
  "csv_url": null,
  "error": "sql_generation_failed: column 'district' not found in schema"
}
```

---

### GET /api/download-csv?session_id=<id>
Download the query result as a comma-separated file.

**Response:** `text/csv` with `Content-Disposition: attachment`

---

### GET /api/schema
Return the introspected DB schema summary (used by the frontend to hint which tables exist).

**Response**
```json
{
  "tables": [
    {
      "name": "fir_registry",
      "columns": [
        {"name": "fir_id", "type": "int", "nullable": false},
        {"name": "district", "type": "nvarchar(100)", "nullable": true},
        ...
      ]
    }
  ],
  "source": "mssql|sqlite_dev|sqlite_fallback"
}
```

---

## Rate Limiting

No hard rate limit in Phase 1. Max concurrent queries per client: 1 (subsequent requests return 429 with `Retry-After: 5`). This is enforced at the FastAPI route level to protect the DB from parallel storm runs.

## Timeouts

- LLM call per node: 30 seconds
- DB query execution: 60 seconds
- Total /api/query timeout: 90 seconds (FastAPI response timeout)
