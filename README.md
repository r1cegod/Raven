**Raven** is a private source-signal workbench for reviewing public learning
material.

The first version is small on purpose: collect public source metadata, store
candidate records in a local SQLite workbench, and let a human review which
sources are worth attention.

### Phase 1

```text
search query
  -> public metadata candidates
  -> local SQLite workbench
  -> human review
  -> review criteria updates
```

### Candidate Shape

```text
source
platform_id
platform_title_or_label
short_preview_when_available
link
author_or_channel
published_at
source_metric
```

### Reddit Boundary

Reddit support is pending official API access. The intended Reddit adapter is a
read-only metadata search adapter that links back to Reddit for review.

Out of scope for the Reddit adapter:

- posting, commenting, voting, or messaging
- subreddit moderation actions
- public API access over Reddit data
- long-term Reddit content storage
- user profiling
- model training on Reddit data

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

### Current Boundary

SQLite storage is the active backend foundation.
YouTube `search.list` plus first normalization pass are active and smoke-tested.
Reddit search is a platform-gated source adapter until official API access is
approved.

Only metadata search and local review are active at this stage.

### Development History

See `logs/DEV_LOG.md`.

*Built by Anh Duc*
