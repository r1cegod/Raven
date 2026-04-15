"Nga you aint making 10k/month with that 1 week vibecoded sloppy shit"
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
Nope ya can't use this yet.

### Current Boundary
No crawler yet. No YouTube/Reddit API wiring yet.
No backend/frontend implementation yet.

The first useful scaffold is the detector loop:

Raven prediction -> Silently rates -> I rate -> Enforce

### Development History
See `logs/DEV_LOG.md`.

*Built by Anh Duc*