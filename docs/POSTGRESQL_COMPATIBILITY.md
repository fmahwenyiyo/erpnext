# PostgreSQL Compatibility Report

Date: 2026-08-12

See [TECHNICAL_AUDIT.md](TECHNICAL_AUDIT.md) for how this fits into the overall audit, and
[TEST_REPORT.md](TEST_REPORT.md) for live-environment (Docker) verification status.

## Versions

| Component | Version |
|---|---|
| ERPNext | `17.x.x-develop` (this checkout, commit `53d3ba7a...` at audit start) |
| Frappe Framework | `develop` branch (pinned by `pyproject.toml` to `>=17.0.0-dev,<18.0.0`) |
| PostgreSQL | 16 (as pinned in `docker-compose.local.yml`'s `db` service; CI uses whatever `postgres` version ships preinstalled on `ubuntu-latest`, currently also 16.x) |
| Python | 3.14 |

## PostgreSQL site creation command

Exact command this repo's own CI (`.github/helper/install.sh`) and the local Docker Compose stack
(`docker-compose.local.yml`'s `create-site` service) both use:

```sh
bench new-site --db-type postgres \
  --db-host <postgres-host> \
  --db-name <dbname> \
  --db-password <password> \
  --db-root-username postgres \
  --db-root-password <postgres-root-password> \
  --admin-password <admin-password> \
  --install-app erpnext \
  --set-default <site-name>
```

## Database configuration used

`.github/helper/site_config_postgres.json` (CI) / `docker-compose.local.yml` (local):
`db_type: postgres`, UTF-8 (PostgreSQL's default server encoding), `PGTZ=UTC`/`TZ=UTC` set on the
`db` container so all timestamps are stored and compared in UTC, consistent with Frappe's own
timezone handling. No non-standard connection-pool or extension requirements.

## Existing PostgreSQL compatibility infrastructure (found, not built by this audit)

This ERPNext checkout already has mature, actively maintained PostgreSQL support — see
[TECHNICAL_AUDIT.md §3](TECHNICAL_AUDIT.md#3-database-specific-code-and-existing-postgresql-support)
for the full inventory: `.github/POSTGRES_COMPATIBILITY.md` (rulebook), `.github/helper/postgres_compat.py`
(static AST checker, wired into pre-commit), `.github/workflows/server-tests-postgres.yml` (full
CI suite on Postgres, label-gated + nightly), `.greptile/config.json` (AI review context).

## Static audit results

Ran the project's own `.github/helper/postgres_compat.py` against every file it is scoped to
cover (matching the `postgres-compat` pre-commit hook exactly):

| Scope | Files scanned | Violations |
|---|---|---|
| `erpnext/**/*.py` excluding `erpnext/patches/` | 2,472 | **0** |
| `erpnext/patches/**/*.py` (informational — intentionally out of the gate's scope) | 453 | 21 |

The 21 patch-directory hits (`UPDATE...JOIN`, SQL `IF()`, `timestamp()`, `date_format()`,
`.rlike()`, one `distinct=True, order_by=`) are all in patches dated `v12_0`–`v16_0`. **Not
fixed, and not a live bug**: a patch only executes once, during an upgrade of an *existing* site
past that version number. PostgreSQL support in ERPNext post-dates all of these version numbers,
so no PostgreSQL-backed site can ever be on a schema old enough to need them — and a fresh
`bench new-site --db-type postgres` installs the current schema directly, never replaying the
incremental patch chain. Rewriting them would touch historical migration code for zero behavioural
benefit on any real Postgres install, which the audit's own ground rules (fix root causes, don't
touch code outside the actual problem, preserve upgradeability) argue against.

## Semantic-divergence audit (the part the static checker cannot cover)

The static checker deliberately only catches *mechanical* breaks (constructs that error on
PostgreSQL). It explicitly does not — and cannot — catch *semantic* divergences: queries that
succeed on both engines but return different results (loose `GROUP BY`, case-sensitive text
comparisons, NULL ordering, division-by-zero, `IfNull` type mismatches, unguarded catch-and-continue
inserts). A manual/agent-assisted pass covered these categories across all non-patch, non-test
`erpnext/**/*.py` files, cross-checked against the rulebook's own false-positive list (§4 of
`.github/POSTGRES_COMPATIBILITY.md`) before reporting anything.

**Result: this codebase's existing Postgres hardening is extensive.** The overwhelming majority of
patterns checked for were already handled correctly, with inline comments in the source
explicitly documenting *why* (functional-dependence justifications for `Max()`/`Min()` wraps,
`NullIf`-guarded divisions, `Lower()`-wrapped case-sensitive lookups, scoped `frappe.db.savepoint()`
guards around catch-and-continue inserts, and even a regression test — `test_asset_depreciations_and_balances.py`
— written specifically to lock in a previously-fixed `IfNull(date_col, 0)` bug). No confirmed
value-changing divergence was found in the current `develop` tree.

Three defensive hardening fixes were applied — see below. None of them were proven to change a
live, observable result today; they bring three call sites in line with a determinism/transaction-safety
convention the codebase already applies everywhere else, closing gaps that would otherwise be one
edge case away from becoming real bugs.

### Fixes made

**1. `erpnext/crm/frappe_crm_api.py` — full rollback instead of a scoped savepoint (real risk class, confirmed precedent)**

```python
# before
except Exception:
    frappe.db.rollback()
# after
except Exception:
    frappe.db.rollback(save_point="crm_create_prospect")
```

Per `.github/POSTGRES_COMPATIBILITY.md` §5: on PostgreSQL, a failed `insert()` aborts the *whole*
transaction (`InFailedSqlTransaction`), so a catch-and-continue handler that recovers with a bare
`frappe.db.rollback()` discards *any* work already committed earlier in the same request — work
MariaDB would have kept. This exact bug class was already found and fixed once in this same file:
`create_customer()` (a few lines below) carries an explicit comment — *"a full rollback would [discard
the Customer just created]; MariaDB kept it pre-migration"* — documenting a prior real incident.
`create_prospect_against_crm_deal()` had the identical shape but had not received the same fix.
Applied the same `frappe.db.savepoint("crm_create_prospect")` / `rollback(save_point=...)` pattern
already used by its sibling `create_address()` two functions below. Regression test added:
`erpnext/crm/test_frappe_crm_api.py` (mocks a failed insert and asserts the recovery path uses the
scoped savepoint, not a bare rollback — so a future revert back to `frappe.db.rollback()` fails CI).

**2. `erpnext/accounts/deferred_revenue.py` — missing ORDER BY tiebreaker**

```python
.orderby(je.posting_date, order=frappe.qb.desc)
+ .orderby(je.name, order=frappe.qb.desc)
.limit(1)
```

**3. `erpnext/assets/doctype/asset/depreciation.py` — missing ORDER BY tiebreaker**

```python
.orderby(depreciation_schedule.schedule_date, order=Order.desc)
+ .orderby(depreciation_schedule.name, order=Order.desc)
.limit(1)
```

Both are `ORDER BY <date> DESC LIMIT 1` queries with no secondary sort key; PostgreSQL and MariaDB
can pick different rows when two rows tie on the ordered date, per §2 of the compatibility rulebook.
**Honest caveat, checked before writing this up**: in both call sites, the *only* field consumed
downstream from the tied query is the sorted-on date column itself (`prev_gl_via_je[0].posting_date`;
`last_depreciation_date[0][0]`, which *is* `schedule_date`) — not an identity column like `name`.
Because the sort key and the consumed value are the same column, a tie by definition means the two
engines return the *same value* regardless of which row wins the tiebreak; there is no reachable
input today that makes these two specific call sites produce different output across engines. These
were applied anyway because they still cost nothing, match the tiebreaker convention this codebase
already uses at multiple other `ORDER BY ... LIMIT 1` call sites (e.g. `exchange_rate_revaluation.py`),
and harden the query against a future edit that starts consuming a non-tied column from the same
result row. **No regression test was added for these two** — a test can only assert "the query still
returns the correct date," which passes identically with or without the fix, so it would not be a
meaningful regression guard (see repo rule: don't write tests that can't fail).

## Live PostgreSQL verification

Static and semantic-code-level auditing is only half the picture — see
[TEST_REPORT.md](TEST_REPORT.md) for whether a real `bench new-site --db-type postgres` install,
migration, and test run were actually exercised on this machine, and the exact PASS/FAIL/BLOCKED/
NOT VERIFIED status of each.

## Remaining compatibility concerns

- The patch-directory hits above are permanently out of scope by design (see rationale above) —
  not a remaining concern, documented here so it isn't mistaken for an oversight.
- The `.github/workflows/server-tests-postgres.yml` CI job is **label-gated** — it does not run on
  every PR by default. Any future PR touching SQL should still get the `postgres` label (or wait
  for the nightly cron) before merge; the static pre-commit hook alone does not catch semantic
  divergences.
- This audit's semantic pass, however thorough, is not a substitute for actually running the full
  server test suite against a live PostgreSQL site (which the label-gated CI job does, and which
  this audit attempted locally via Docker — see TEST_REPORT.md). Static/manual review finds
  *classes* of bugs; it cannot prove the absence of every possible one.

## Deployment recommendation

Use PostgreSQL 16 (matches CI and the local Docker stack), create sites with
`bench new-site --db-type postgres`, and keep the `postgres` PR label / nightly CI job as the
actual correctness backstop for future changes — this audit hardens three edge cases and confirms
the static gate is clean, but the project's own layered defenses (static check + semantic rulebook
+ full CI suite) are the right ongoing mechanism, not a one-time audit.
