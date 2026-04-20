# AGENTS.md - Raven Repo Entry Point

## STOP - Read The Vault First

**Do not read a single file in this repo until you have read:**

```text
D:\ANHDUC\ADUC_vault\ADUC\AGENTS.md
```

The vault is the brain. This repo is the body. Operating on the body without
reading the brain is the failure mode.

The vault holds: current strategy, project state, session start protocol,
loading order, self-healing contract, and dev rules. None of that should be
reconstructed from this repo alone.

**The vault path is the first action of every session. No exceptions.**

---

## Tooling Rules

- Use `rtk` for shell/repo commands where practical. Fall back to raw shell only
  when `rtk` cannot express the command cleanly or would hide needed output.
- Use Obsidian MCP for vault reads/writes instead of raw filesystem access.
- Treat `/home/r1ceg/Raven` as the WSL Raven working repo.

---

## Repo Structure

| Path | Role |
|---|---|
| `src/backend/` | Backend scaffold |
| `src/backend/test/` | Central backend test folder |
| `src/frontend/` | Frontend scaffold |
| `logs/` | Repo-local dev log |

`logs/DEV_LOG.md` is the navigation file. Daily notes live under
`logs/dev/days/`.

---

## Development Rules

### Engineering

- **Bug-First:** fix confirmed breaks before adding features.
- **Bottom-Up Law:** build and verify components in isolation before wiring a
  full pipeline.
- **Test Folder Rule:** backend tests live under `src/backend/test/`; do not add
  root-level `test_*.py` files or a separate root `tests/` tree.
- **One Wire Per Response:** do not dump multiple implementation layers at once.
- **Output Audit:** before writing code, ask whether the code creates the final
  answer or the blueprint to derive it.

### Raven-Specific

- Keep the repo empty until the backend/frontend boundary is chosen.
- Do not add crawler, rubric, CLI, or LLM code before the first backend contract
  is defined.
- Do not store full third-party content as a durable artifact.

### Commands

```bash
git status --short --branch
```
