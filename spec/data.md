# Data Model

## Sources

| Source | Driver | Role | Access |
|---|---|---|---|
| **Operational MsSQL** | `pyodbc` + SQLAlchemy | Primary data store | Read-only, SELECT-only service account |
| **Local SQLite** | `aiosqlite` | Audit log + dev fallback + session state | Read-write, local file |

## Operational MsSQL Schema (agent-facing view)

The agent does **not** need to know every table. It uses live schema discovery (`sp_columns`, `INFORMATION_SCHEMA`) at graph startup to populate its context. The canonical tables it reasons over:

| Table | Key columns (example) | Notes |
|---|---|---|
| `fir_registry` | `fir_id`, `district`, `station`, `registered_at`, `section`, `status` | One row per FIR |
| `challan_log` | `challan_id`, `district`, `offence_type`, `issued_at`, `amount` | Traffic challan data |
| `officer_assignments` | `officer_id`, `district`, `designation`, `posted_at` | Officer posting history |
| `daily_diary` | `entry_id`, `station`, `entry_date`, `summary` | Free-text daily diary |

**Phase 1 assumption:** The agent introspects `INFORMATION_SCHEMA.TABLES` + `INFORMATION_SCHEMA.COLUMNS` at startup and caches the schema summary in memory. No manual schema registration is required.

### Access Controls

- **Service account:** `SELECT` only on operational tables. No `INSERT/UPDATE/DELETE/EXEC` rights.
- **Sensitive columns** (e.g. complainant name, accused details): Phase 1 assumes no column-level masking; the officer sees whatever the service account can see. Column-masking policy is a Phase 3 item.
- **Row-level security:** Not enforced by the agent. Enforced by the DB itself via the service account's schema/row permissions. Agent scope is bounded by what the service account can `SELECT`.

## Local SQLite Schema

### `audit_log`

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `timestamp` | DATETIME | UTC |
| `officer_id` | TEXT | Omitted or `"anonymous"` in Phase 1 |
| `question` | TEXT | Raw NL question |
| `sql` | TEXT | The SQL actually executed |
| `row_count` | INTEGER | Number of rows returned |
| `duration_ms` | INTEGER | Wall-clock execution time |
| `error` | TEXT | NULL if clean; error message otherwise |
| `llm_provider` | TEXT | e.g. `anthropic/claude-3-5-sonnet` |
| `token_usage` | TEXT | JSON: `{prompt, completion, total}` |

### `query_cache` (Phase 1, in-memory in Phase 2+)

| Column | Type | Notes |
|---|---|---|
| `question_hash` | TEXT PK | SHA-256 of normalised question |
| `sql` | TEXT | Generated SQL |
| `result_json` | TEXT | JSON-serialised rows |
| `created_at` | DATETIME | When cached |
| `hit_count` | INTEGER | Times this cache entry was served |

## PII Handling

- No PII is transmitted to the LLM beyond the column names and the operator's NL question.
- Result rows **are** on-prem only; they never leave the box.
- Audit log is local SQLite; retention policy is operational — default "keep while useful", no auto-purge in Phase 1.

## Data Freshness

- The MsSQL query always hits the live DB (no replica lag in Phase 1).
- CSV uploads (Phase 2) create a transient SQLite table; they are not merged into the operational DB.
