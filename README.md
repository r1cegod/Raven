**Raven** is a private source-signal workbench for turning a rich research
request into auditable source candidates for Codex.

Raven is not the general agent brain. It owns source acquisition, metadata
filtering, local evidence logs, and source packets.

## Current Flow

```text
rich request
  -> enricher
      -> generated search queries
      -> key_words for title filtering
  -> YouTube search
      -> search.list + videos.list enrichment
      -> local SQLite run/query/API/candidate logs
  -> ranker_tier1
      -> binary request-relatedness gate
      -> final_decision = keep | throw_out
  -> ranker_tier1_final
      -> high-model priority labeler
      -> sexy_label = maybe | click | must_click
  -> Tier 2 source packet lane
```

Naming boundary:

```text
request
  -> user intent object / graph input / raven_runs.request

queries
  -> generated search strings / raven_queries.query
```

There is no original `query` or `target` input path.

## Active Contract

- Tier 1 is a wide recall gate. It should only remove clearly unrelated videos.
- Final owns metadata priority judgment.
- The local SQLite DB is a disposable workbench and is ignored by Git.
- Generated eval packets/checkpoints/live outputs are ignored by Git.
- Eval harness code and JSONL fixtures are source files and should be tracked.

## Tech Stack

- Backend: `src/backend/`
- Observability/evals: `src/backend/observability/` and `eval/`
- Backend tests: `src/backend/test/`
- Logs: `logs/DEV_LOG.md`

## How To Use

Use the repo venv:

```bash
./.venv/bin/python -m unittest src.backend.test.test_enricher_contract
```

Run focused evals:

```bash
./.venv/bin/python eval/run_observation.py dataset --suite enricher --file eval/enricher_request_cases.jsonl --mode single
./.venv/bin/python eval/run_observation.py dataset --suite ranker_tier1 --file eval/ranker_tier1_request_cases.jsonl --mode single
./.venv/bin/python eval/run_observation.py dataset --suite ranker_tier1_final --file eval/ranker_tier1_final_request_cases.jsonl --mode single
```

Run a full request:

```bash
./.venv/bin/python eval/run_observation.py full --graph raven --request "<rich request>"
```

Read an existing run:

```bash
./.venv/bin/python eval/run_observation.py read-run --graph raven --run-id <id>
```

## Current Platform Boundary

YouTube metadata search is active.

Reddit support is not active. The intended Reddit adapter remains read-only
metadata search that links back to Reddit for review. Out of scope:

- posting, commenting, voting, or messaging
- subreddit moderation actions
- public API access over Reddit data
- long-term Reddit content storage
- user profiling
- model training on Reddit data

## Development History

See `logs/DEV_LOG.md`.

*Built by Anh Duc*
