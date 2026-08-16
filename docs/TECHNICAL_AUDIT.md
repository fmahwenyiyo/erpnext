# ERPNext Technical Audit

Date: 2026-08-12
Auditor: Claude Code (automated engineering audit)
Repository: `e:\Projects\GitHub\erpnext` (fork: `fmahwenyiyo/erpnext`, upstream: `frappe/erpnext`)

This document records the state of the repository **as found**, before any fixes were applied.
See [FORK_CHANGES.md](FORK_CHANGES.md) for what was subsequently changed and why.

---

## 1. Identity and versions

| Item | Value | Source |
|---|---|---|
| ERPNext version | `17.x.x-develop` | `erpnext/hooks.py: develop_version` |
| ERPNext branch | `develop` | `git branch --show-current` |
| ERPNext commit (HEAD at audit start) | `53d3ba7a7820e3c09b24a698149a63ecfc523e84` | `git log -1` |
| Required Frappe Framework version | `>=17.0.0-dev,<18.0.0` | `pyproject.toml: [tool.bench.frappe-dependencies]` |
| Frappe branch used by CI | `develop` (frappe/frappe) | `.github/helper/install.sh` (`FRAPPE_BRANCH` default) |
| Required Python | `>=3.14` | `pyproject.toml: [project] requires-python` |
| Python pinned in CI | `3.14` | `.github/workflows/server-tests-postgres.yml: PYTHON_VERSION` |
| Node.js in CI | `24` | `.github/workflows/server-tests-postgres.yml` |
| Package manager | `yarn` (via `banking/` subproject `postinstall`), no root lockfile beyond `yarn.lock` (mostly empty — no root JS deps) | `package.json`, `yarn.lock` |
| Build backend | `flit_core` (Python), `bench build` (frontend assets) | `pyproject.toml` |

**Local machine, as found (no execution environment beyond the bare app checkout):**

| Tool | Present locally? | Version |
|---|---|---|
| Python | Yes | 3.14.3 (matches `requires-python`) |
| Node.js | Yes | v24.13.0 (matches CI) |
| Yarn | **No** | not installed |
| pip | **No** (no `pip` on PATH; only the Windows Store Python shim) | — |
| Docker / Docker Compose | Yes | Docker 29.4.0, Compose v5.1.1 |
| bench (frappe-bench CLI) | **No** | not installed |
| Frappe framework source | **No** | not present, not a sibling checkout |
| PostgreSQL client (`psql`) | **No** | not installed |
| Redis (`redis-cli`) | **No** | not installed |

**Conclusion:** this checkout is the bare `erpnext` app repository only — there is no bench, no
Frappe framework source, and no local Postgres/Redis/Python toolchain. The only real execution
path available on this machine is **Docker**. This shaped the verification strategy documented in
[TEST_REPORT.md](TEST_REPORT.md): static analysis and code fixes were done directly against this
checkout; live-environment verification (site creation, migrations, module/workflow testing) was
attempted via a Docker Compose stack that builds a bench from this checkout's actual source rather
than pulling a prebuilt release image.

---

## 2. Redis / PostgreSQL / worker / scheduler / realtime architecture

ERPNext itself does not define this architecture — it inherits Frappe's, and only *consumes* it
(background jobs via `frappe.enqueue`, `scheduler_events` in `hooks.py`, realtime via
`frappe.publish_realtime`). Nothing in `erpnext/hooks.py` overrides queue/scheduler/realtime
wiring. As designed by Frappe:

- **Redis**: two logical instances — `redis_cache` and `redis_queue` (queue also backs realtime
  pub/sub unless `redis_socketio` is set separately). Required, no fallback.
- **Background workers**: `bench worker --queue short,default,long` (RQ-based), started as
  separate OS processes/containers per queue.
- **Scheduler**: `bench schedule` (a single long-running process that enqueues `hooks.py:
  scheduler_events` on their cron-like cadence — hourly/daily/weekly/monthly/cron entries).
  ERPNext registers dozens of scheduled jobs in `erpnext/hooks.py` (subscription renewal,
  scheduled report emails, exchange rate updates, POS reconciliation reminders, etc.).
- **Realtime**: Frappe's Node `socketio.js` process, backed by Redis pub/sub, fronted by the
  reverse proxy on `/socket.io` with WebSocket upgrade support.
- **Web/app server**: `bench start` (Werkzeug dev server) for development only; production uses
  gunicorn behind nginx — never the dev server (confirmed absent from any of this repo's
  production-facing config; the only dev-server reference is in `README.md`'s local dev
  instructions).

## 3. Database-specific code and existing PostgreSQL support

This is the most important finding of the audit: **PostgreSQL support in this codebase is not a
gap to be filled — it is a mature, actively maintained, CI-gated feature.**

Found already in the repository:

- **`.github/POSTGRES_COMPATIBILITY.md`** — a detailed, example-rich rulebook of every MariaDB/
  PostgreSQL divergence class (hard breaks that error, silent semantic divergences, the
  "GROUP BY / DISTINCT row-count trap", transaction/savepoint discipline, refactor-faithfulness).
  States the governing rule explicitly: *"MariaDB behaviour must not change; PostgreSQL is brought
  into line with MariaDB — never the reverse."*
- **`.github/helper/postgres_compat.py`** — an AST-based static checker for the *mechanical*
  hard-break patterns (MySQL-only functions, `UPDATE...JOIN`, `RLIKE`, bool-into-Check-column,
  `CAST AS CHAR`, distinct+order_by, `SHOW INDEX` result keys, etc.), wired into
  **`.pre-commit-config.yaml`** as the `postgres-compat` local hook, scoped to `erpnext/**/*.py`
  and explicitly excluding `erpnext/patches/` (historical, version-gated migrations that only ever
  run against a pre-existing MariaDB install being upgraded — out of scope for a Postgres gate).
- **`.github/workflows/server-tests-postgres.yml`** — a full CI job that builds a bench, creates a
  PostgreSQL-backed `test_site`, and runs the entire ERPNext server test suite across 4 parallel
  shards. It is **label-gated** (`postgres` label on the PR) plus a nightly cron — it does not run
  on every PR, which is exactly why the static checker and this audit matter.
  `.github/helper/site_config_postgres.json` and `start-db.sh` show the exact CI DB config.
- **`.greptile/config.json`** — wires the same rulebook into AI code review as standing PR context.
- **`semgrep/test-correctness.yml`** — unrelated to Postgres; guards test idempotency
  (no `frappe.db.commit()`/`frappe.db.truncate()` in tests, no `tearDown()` override without
  `super().tearDown()`).

### 3.1 Static audit performed

Ran `.github/helper/postgres_compat.py` — the project's own mechanical checker — against every
`*.py` file it is scoped to cover:

- **`erpnext/**/*.py` excluding `erpnext/patches/`** (2,472 files, matching the pre-commit hook's
  exact scope): **0 violations.**
- **`erpnext/patches/**/*.py`** (453 files, informational — intentionally excluded from the gate):
  **21 hits**, all in patches dated `v12_0`–`v16_0` (`UPDATE...JOIN`, SQL `IF()`, `timestamp()`,
  `date_format()`, `.rlike()`, one `distinct=True, order_by=`). These are legitimately out of
  scope: a patch only executes once, during an *upgrade* of an existing site past that version
  number; PostgreSQL support in ERPNext post-dates all of these, so a Postgres site can never have
  been on a pre-v12–v16 schema needing them, and a fresh `bench new-site --db-type postgres`
  never runs the incremental patch chain at all (it installs the current schema directly). No fix
  applied — confirmed not a live bug, documented here rather than "fixed" to avoid rewriting
  historical migration history for no behavioural benefit (see repo rule: don't touch code outside
  the actual problem).

A second pass covered the **semantic divergences the static checker explicitly does not and
cannot catch** (loose `GROUP BY`, case-sensitive comparisons on free-text columns, division by a
possibly-zero divisor, integer-division truncation, `IfNull`/`Coalesce` type mismatches,
catch-and-continue inserts without savepoints). Findings and fixes are in
[POSTGRESQL_COMPATIBILITY.md](POSTGRESQL_COMPATIBILITY.md).

## 4. Existing Docker configuration

- **In this repo**: one untracked file, `docker-compose.local.yml` (present before this audit
  began, not committed). It defines a full frappe_docker-style topology (backend, frontend/nginx,
  websocket, queue-short, queue-long, scheduler, configurator, create-site, PostgreSQL 16, two
  Redis instances) — **but every app-image service pulls the prebuilt upstream
  `frappe/erpnext:v16.31.1` image**, not a build of this checkout. Two problems: (a) it never
  exercises this repository's actual `develop` source or any fix made here, and (b) v16.31.1 is a
  different major version than this checkout's `17.x.x-develop`, so it isn't even testing
  compatible code. Addressed in [FORK_CHANGES.md](FORK_CHANGES.md) — replaced with a build that
  compiles a bench from this checkout's source plus a matching Frappe `develop` checkout.
- **Not in this repo**: no `Dockerfile`/`Containerfile`, no `.dockerignore`. Official ERPNext
  Docker images are built externally, by the `frappe_docker` repository — this repo only
  *triggers* that build on release (`.github/workflows/docker-release.yml` POSTs to
  `frappe/frappe_docker`'s `core-build-stable.yml` on GitHub Release). This confirms the correct
  approach per the frappe/ERPNext deployment architecture: production containers should follow
  `frappe_docker`'s layout rather than a bespoke one.

## 5. CI/CD (`.github/workflows/`)

19 workflows. Relevant to this audit:

| Workflow | Purpose |
|---|---|
| `server-tests-mariadb.yml` / `server-tests-mariadb-faux.yml` | Full server test suite on MariaDB, always-on |
| `server-tests-postgres.yml` | Same suite on PostgreSQL, **label-gated + nightly cron only** |
| `linters.yml` | ruff, eslint, pre-commit (includes `postgres-compat`) |
| `run-individual-tests.yml` | on-demand single-module test runs |
| `build-and-commit-assets.yml` | frontend asset build |
| `docker-release.yml` | triggers `frappe_docker` image build on GitHub Release |
| `patch.yml` / `patch_faux.yml` | patch-related checks |
| `docs-checker.yml` | documentation link/format checks |

No workflow currently *deploys* anywhere — CI is build/test/lint only, consistent with the
requirement not to auto-deploy to production.

## 6. Custom apps / modifications

None found. This is a straight fork of `frappe/erpnext` on `develop` — no additional custom app
directories, no `hooks.py` overrides pointing at a separate custom app, no vendored patches beyond
upstream's own `erpnext/patches/`. The only local, uncommitted addition at audit start was the
untracked `docker-compose.local.yml` described above.

## 7. Security-sensitive configuration observed

- No hardcoded credentials, API keys, or secrets found in `erpnext/**/*.py` (targeted grep for
  `password/secret/api_key` literal assignments, excluding test/password-reset code, returned zero
  hits).
- `.gitignore` does not yet list `.env` (no root-level env-file workflow existed before this
  audit — site secrets normally live in `sites/<site>/site_config.json` outside this repo, in the
  bench). Addressed when introducing `.env.example` for the new Docker Compose setup — see
  [FORK_CHANGES.md](FORK_CHANGES.md).
- Auth/permissions/CSRF/CORS/session handling is entirely Frappe framework responsibility, not
  ERPNext app code — see [SECURITY_REVIEW.md](SECURITY_REVIEW.md) for what was and wasn't
  verifiable at the ERPNext layer without a running instance.

## 8. Test framework

Standard Frappe test runner (`bench --site <site> run-tests` / `run-parallel-tests`), built on
`unittest` via `frappe.tests.utils.FrappeTestCase`. Test suite lives under
`erpnext/**/test_*.py` and `erpnext/**/*/test/`. `erpnext/tests/bootstrap_test_data` is used by CI
to pre-seed shared test data before sharded parallel runs. No pytest, no separate JS/Cypress
frontend test suite found in this repo (frontend behavior is largely covered by Frappe's own
framework-level tests, not duplicated here).

## 9. Deprecated APIs

`erpnext/deprecation_dumpster.py` exists and is explicitly excluded from the
`function_type_validation` check in `pyproject.toml` — it's the project's own designated holding
area for deprecated-but-not-yet-removed functions, not an audit finding in itself.

## 10. Summary of what this audit changed vs. only documented

This audit **ran the project's own tooling for real** rather than re-deriving PostgreSQL
compatibility rules from scratch, per the task's explicit instruction not to reinvent checks
ERPNext already provides. Concrete fixes made as a result are tracked in
[FORK_CHANGES.md](FORK_CHANGES.md); live-environment (Docker/Postgres) verification results,
including anything that could **not** be verified on this machine, are in
[TEST_REPORT.md](TEST_REPORT.md) with explicit PASS/FAIL/BLOCKED/NOT VERIFIED status per area.
