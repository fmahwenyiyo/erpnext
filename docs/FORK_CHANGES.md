# Fork Changes

Tracks every change this audit made to the upstream ERPNext `develop` behavior/tooling, why, and
what covers it. Goal: keep this fork's delta from `frappe/erpnext` small, documented, and easy to
drop when rebasing onto a future upstream `develop`.

---

## Code changes (behavioral)

### 1. `erpnext/crm/frappe_crm_api.py`

- **What changed**: `create_prospect_against_crm_deal()`'s exception handler now uses
  `frappe.db.savepoint("crm_create_prospect")` / `frappe.db.rollback(save_point="crm_create_prospect")`
  instead of a bare `frappe.db.rollback()`.
- **Upstream behaviour**: a failed `Prospect.insert()` (e.g. a race on the `company_name`
  uniqueness check) recovered with a full transaction rollback.
- **New behaviour**: recovery is scoped to a savepoint, matching the pattern already used by the
  sibling functions `create_customer()` (see its `crm_customer_links` savepoint and inline comment
  documenting the exact same prior bug) and `create_address()` in the same file.
- **Reason**: on PostgreSQL, a failed `insert()` poisons the whole transaction
  (`InFailedSqlTransaction`); a full `frappe.db.rollback()` recovers it but also discards any DB
  work already committed earlier in the same request — a silent regression relative to MariaDB,
  which has no equivalent statement-abort behaviour. See
  [POSTGRESQL_COMPATIBILITY.md](POSTGRESQL_COMPATIBILITY.md) for the full rationale.
  MariaDB behaviour is unchanged (a scoped-savepoint rollback and a full rollback are identical
  when nothing preceded the failing statement, which remains true for this call site today).
- **Tests covering the change**: `erpnext/crm/test_frappe_crm_api.py` (new file) — mocks a failed
  `Prospect.insert()` and asserts the handler calls `frappe.db.savepoint("crm_create_prospect")`
  and `frappe.db.rollback(save_point="crm_create_prospect")`, not a bare rollback.
  **NOT VERIFIED by execution** — no local bench/site was available to actually run
  `bench run-tests`; see [TEST_REPORT.md](TEST_REPORT.md). The test does compile and pass the
  project's own static checks.

### 2. `erpnext/accounts/deferred_revenue.py`

- **What changed**: added `.orderby(je.name, order=frappe.qb.desc)` as a secondary sort key after
  the existing `.orderby(je.posting_date, order=frappe.qb.desc)` in `get_booking_dates()`'s lookup
  of the previous deferred-revenue Journal Entry.
- **Reason**: defensive determinism fix — see the honest caveat in
  [POSTGRESQL_COMPATIBILITY.md](POSTGRESQL_COMPATIBILITY.md#fixes-made): the only field consumed
  from the tied row is the sorted-on `posting_date` itself, so this does not change observable
  output today, but matches the tiebreaker convention used elsewhere in this codebase
  (e.g. `exchange_rate_revaluation.py`) and guards against a future edit that starts consuming
  `.name` from the same result.
- **MariaDB impact**: none (adding a tiebreaker only resolves previously-arbitrary ties).
- **Tests covering the change**: none added — see rationale in POSTGRESQL_COMPATIBILITY.md
  (a test here could not meaningfully fail).

### 3. `erpnext/assets/doctype/asset/depreciation.py`

- **What changed**: added `.orderby(depreciation_schedule.name, order=Order.desc)` as a secondary
  sort key in `get_last_depreciation_date()`.
- **Reason / MariaDB impact / tests**: identical rationale to item 2 above.

---

## Tooling / infrastructure changes (non-behavioral)

### 4. `docker-compose.local.yml` — rebuilt to test this repo's actual source

- **Found as**: an untracked file already present at audit start, pulling the prebuilt
  `frappe/erpnext:v16.31.1` image for every app-role service (backend, frontend, workers,
  scheduler, websocket).
- **Problem**: v16.31.1 is a different major version than this checkout (`17.x.x-develop`), and
  since it's a prebuilt image, it never ran this repository's code at all — any local fix
  (including items 1–3 above) would be invisible to it.
- **New behaviour**: every app-role service now builds from `Containerfile` (new), which installs
  ERPNext from *this checkout's actual source* using the same mechanism this project's own CI uses
  to test uncommitted changes (`.github/helper/install.sh`: `bench get-app erpnext
  "${GITHUB_WORKSPACE}"` — `bench get-app` accepts a local path and clones it like any git remote).
  Also added: `.env`-driven configuration (no hardcoded credentials — see `.env.example`), health
  checks on `db`/`redis-*`/`backend`/`frontend`, `restart: unless-stopped` policies, and a shared
  build definition via a YAML anchor so the image is built once and reused across all app-role
  services.
- **Tests covering the change**: attempted a real `docker compose build` + `up` +
  `bench new-site --db-type postgres` + `bench migrate` run — see
  [TEST_REPORT.md](TEST_REPORT.md) for the actual PASS/FAIL/BLOCKED result (this doc is written
  before that run completes; do not treat this entry as proof the stack works end-to-end).

### 5. `Containerfile` (new)

- Adapted from frappe_docker's `images/production/Containerfile`
  (github.com/frappe/frappe_docker, MIT licensed) per the task's explicit instruction to base
  production Docker deployment on the official Frappe/ERPNext Docker architecture rather than an
  invented topology. One deliberate deviation from upstream, documented in the file's own header
  comment: erpnext is installed from the local build context instead of
  `https://github.com/frappe/erpnext`, so local fixes are actually exercised.
- `docker/resources/{main-entrypoint.sh,start.sh,nginx/*}` (new) — vendored, unmodified, from the
  same upstream `resources/core/` directory (needed by the Containerfile; not present anywhere in
  this repo before).

### 6. `.gitattributes` (new)

- **Problem found**: this repo has `core.autocrlf=true` and no `.gitattributes`, so Git would
  silently rewrite the new LF-only shell scripts (`docker/resources/**/*.sh`, `Containerfile`,
  `docker-compose.local.yml`) to CRLF on any Windows checkout — which breaks `#!/bin/bash`
  shebangs and shell parsing the moment they're `COPY`'d into a Linux container.
  This was a real, reproducible bug in the repository's line-ending configuration, not specific to
  the files added by this audit — any future shell script added to this repo on a Windows clone
  would hit the same failure.
- **Fix**: force LF for `*.sh`, `Containerfile`, `docker-compose*.yml`, `*.conf` regardless of
  platform `core.autocrlf` setting.

### 7. `.env.example` (new) / `.gitignore`

- Added `.env.example` (placeholders only, categorized per the task's required grouping:
  PostgreSQL / Redis / Frappe-ERPNext / domain-TLS / email / backup / optional integrations).
- Added `.env`, `.env.*` (except `.env.example`), and `/backups/` to `.gitignore` — none of these
  existed before since the repo had no root-level env-file workflow prior to this audit's Docker
  setup.

### 8. `docs/` (new directory)

- `TECHNICAL_AUDIT.md`, `POSTGRESQL_COMPATIBILITY.md`, `FORK_CHANGES.md` (this file),
  `SECURITY_REVIEW.md`, `TEST_REPORT.md`, `BACKUP_RESTORE.md` — required deliverables, all net-new.

### 9. `DEPLOYMENT.md` (new, repo root)

- Required deliverable, net-new.

---

## Explicitly NOT changed (and why)

- **`erpnext/patches/**`** — 21 static-checker hits in `v12_0`–`v16_0` patches, left untouched.
  These are historical, version-gated migrations that can never run against a PostgreSQL site (see
  [POSTGRESQL_COMPATIBILITY.md](POSTGRESQL_COMPATIBILITY.md) for the full reasoning). Rewriting
  them would touch dead-for-Postgres migration history for no live benefit, contrary to this
  audit's own "fix root causes, don't touch code outside the actual problem" ground rule.
- **No Frappe framework code was touched** — this repo does not vendor Frappe; the framework is
  fetched fresh (`--frappe-branch=develop`) by the Containerfile build, unmodified.
- **No dependency/version upgrades** — `pyproject.toml`'s `requires-python = ">=3.14"` and
  `frappe = ">=17.0.0-dev,<18.0.0"` pins were left exactly as found; this audit did not judge any
  version change necessary.
