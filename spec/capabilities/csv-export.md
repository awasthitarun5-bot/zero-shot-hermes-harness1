# CSV Result Export

## What It Does
Generates a comma-separated file from the query result set and serves it as a download attachment.

## Inputs
- `rows` (list[dict]) — the result rows from `execute_node`
- `columns` (list[str]) — column headers
- `session_id` (str) — unique identifier for this query session

## Outputs
- `text/csv` HTTP response with `Content-Disposition: attachment; filename="query-<session_id>.csv"`

## External Calls
None. In-memory construction from the already-materialised result set.

## Error Cases
| Error | Handling |
|---|---|
| `rows` is empty | Returns a CSV with only the header row and a companion text note: "< 1 row returned — no data to export." |
| Result set exceeds 1000 rows | Cadenced at the execute_node; CSV always reflects what was actually returned (<=1000 rows) |

## Success Criteria
- After any successful query, the "Download CSV" link produces a valid UTF-8 CSV that opens correctly in Excel/LibreOffice Calc
- CSV column order matches the order shown in the data table
