"When will people understand only AI can debug AI code?"

**Raven** is a Knowledge Signal Engine. It ranks public sources, extracts claims,
records Duc's rating, and turns the disagreement into a sharper detector (for now).

### Purpose
Most knowledge tools help you consume more. That is not the goal.
Raven exists to formalize the bullshit detector:

Get metadatas -> Rate -> Get raw data -> Rate again -> report -> ingest

### Build phases
1. Raven metadata ranker and ME in the loop.
2. Raven reads the raw data -> rate -> ingest.
3. Put everything together.

### Tech Stack
- **Backend:** `src/backend/`
- **Frontend:** `src/frontend/`
- **Logs:** `logs/DEV_LOG.md`

### How To Use
Active Raven is still being built from the backend upward.

Use the repo venv for backend checks:

```bash
./.venv/bin/python -m py_compile src/backend/db.py src/backend/search/youtube_search.py
```

Current YouTube search smoke shape:

```bash
./.venv/bin/python - <<'PY'
from src.backend.search.youtube_search import youtube_search
result = youtube_search("<query>", max_results=1)
print(result)
PY
```

Reference-only API/search code lives in:

```text
docs/reference/metadata_discovery_workbench/
```

Do not treat that folder as production code.

### Current Boundary
SQLite storage is the active backend foundation.
YouTube `search.list` call + first normalization pass are active and live-smoke verified.
Next target: commit one YouTube search result into SQLite.
Reddit search is still pending.
No crawler, rater, raw-content fetcher, frontend, or report generator yet.

The first useful scaffold is the detector loop:

Raven prediction -> Silently rates -> I rate -> Enforce

### Development History
See `logs/DEV_LOG.md`.

*Built by Anh Duc*
