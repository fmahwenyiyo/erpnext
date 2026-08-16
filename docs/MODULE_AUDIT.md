# ERPNext Module Presence and Integrity Audit

Date: 2026-08-12
ERPNext version: `17.x.x-develop` (`erpnext/hooks.py: develop_version`), branch `develop`,
commit `53d3ba7a7820e3c09b24a698149a63ecfc523e84` (shallow clone, depth 1 — see
[Method and limitations](#method-and-limitations)).

**Scope note**: this audit is code-level and metadata-level. A live PostgreSQL site/Desk UI check
was in progress (see [TEST_REPORT.md](TEST_REPORT.md)) but was stopped mid-run at the user's
explicit instruction before `bench new-site`/`bench migrate` completed, in favor of this audit.
Everything below that would normally require a running site (database metadata sync, Desk
UI/Workspace rendering, live permission checks) is marked **NOT VERIFIED** rather than assumed —
see [Section 6-8: what could not be verified live](#sections-6-8-database-ui-and-permission-checks---not-verified-live).

---

## 1. Expected module inventory

The authoritative source is `erpnext/modules.txt` — this is what Frappe reads to register
`Module Def` records for the `erpnext` app on install/migrate. **21 modules**, all present as
directories:

```
Accounts, CRM, Buying, Projects, Selling, Setup, Manufacturing, Stock, Support, Utilities,
Assets, Portal, Maintenance, Regional, ERPNext Integrations, Quality Management, Communication,
Telephony, Bulk Transaction, Subcontracting, EDI
```

Directories that exist under `erpnext/` but are **not** in `modules.txt` (`config`, `controllers`,
`templates`, `www`, `public`, `startup`, `commands`, `change_log`, `gettext`, `locale`, `tests`,
`patches`, `domains`, `desktop_icon`, `workspace_sidebar`, `report_center`, `shopping_cart`) are
supporting/shared code, not Frappe modules — they have no `Module Def` and are correctly excluded
from this inventory, not a sign of a missing/orphaned module.

## 2–3. Module-by-module verification

Directory existence, DocType/controller counts, and shipped-metadata counts (`find`-based,
verified against actual `.json` files, not assumed from folder names):

| Module | Dir Present | DocTypes | Controllers | Reports | Workspace | Dashboard Charts | Print Formats | Fixtures | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Accounts | Yes | 191 | 191/191 | 52 | 4 | 7 | 37 | N/A* | PASS |
| CRM | Yes | 28 | 28/28 | 9 | 1 | 7 | 0 | N/A* | PASS |
| Buying | Yes | 19 | 19/19 | 10 | 1 | 4 | 12 | N/A* | PASS |
| Projects | Yes | 15 | 15/15 | 5 | 1 | 2 | 0 | N/A* | PASS |
| Selling | Yes | 20 | 20/20 | 23 | 1 | 4 | 15 | N/A* | PASS |
| Setup | Yes | 40 | 40/40 | 0 | 2 | 0 | 0 | N/A* | PASS |
| Manufacturing | Yes | 48 | 48/48 | 21 | 1 | 8 | 0 | N/A* | PASS |
| Stock | Yes | 77 | 77/77 | 51 | 1 | 6 | 8 | N/A* | PASS |
| Support | Yes | 11 | 11/11 | 4 | 1 | 0 | 0 | N/A* | PASS |
| Utilities | Yes | 4 | 4/4 | 1 | 0 | 0 | 0 | N/A* | PASS |
| Assets | Yes | 26 | 26/26 | 3 | 1 | 3 | 0 | N/A* | PASS |
| Portal | Yes | 2 | 2/2 | 0 | 0 | 0 | 0 | N/A* | PASS |
| Maintenance | Yes | 5 | 5/5 | 1 | 0 | 0 | 0 | N/A* | PASS |
| Regional | Yes | 5 | 5/5 | 4 | 0 | 0 | 5 | N/A* | PASS |
| ERPNext Integrations | Yes | 1 | 1/1 | 0 | 0 | 0 | 0 | N/A* | PASS |
| Quality Management | Yes | 16 | 16/16 | 1 | 1 | 1 | 0 | N/A* | PASS |
| Communication | Yes | 2 | 2/2 | 0 | 0 | 0 | 0 | N/A* | PASS |
| Telephony | Yes | 5 | 5/5 | 0 | 0 | 0 | 0 | N/A* | PASS |
| Bulk Transaction | Yes | 2 | 2/2 | 0 | 0 | 0 | 0 | N/A* | PASS |
| Subcontracting | Yes | 13 | 13/13 | 0 | 0 | 1 | 0 | N/A* | PASS |
| EDI | Yes | 2 | 2/2 | 0 | 0 | 0 | 0 | N/A* | PASS |

\* No `fixtures` hook or `fixtures/` directory exists anywhere in this app (confirmed by search) —
ERPNext core ships zero pre-built `Workflow` records or fixture exports by design (Workflow is a
user-configured Frappe framework feature); this is expected, not a gap.

**Controller integrity**: verified programmatically, not sampled — all **532** DocType JSON files
across the entire app have a matching `.py` controller file (0 missing). `python -m compileall`
across the entire `erpnext` package found **0 syntax errors**.

**Workspace coverage**: 14 top-level Workspaces exist (`accounting`, `financial_reports`,
`invoicing`, `payments` under Accounts; `assets`, `buying`, `crm`, `manufacturing`, `projects`,
`quality`, `selling`, `stock`, `support`; `erpnext_settings`/`home` under Setup). The 8 modules
with 0 dedicated top-level Workspace (Utilities, Portal, Maintenance, Regional, ERPNext
Integrations, Communication, Telephony, Bulk Transaction, EDI, Subcontracting) were individually
checked, not assumed broken:
- **Subcontracting** doctypes are surfaced as cards inside the Buying/Manufacturing/Stock
  Workspaces (confirmed by grep) — reachable, just not a standalone top-level Workspace. By design.
- **Telephony, Bulk Transaction, EDI, Communication, Utilities, Regional, ERPNext Integrations**
  doctypes are all either Single "Settings" doctypes, backend log/detail tables, or
  admin-utility pages (`Rename Tool`, `Video`, `Plaid Settings`, `Code List`, `Communication
  Medium`, `Call Log`, `Bulk Transaction Log`) — none are `in_create`-flagged end-user creation
  targets that would normally warrant a dedicated Workspace card in standard ERPNext design; they
  are reached via global search or a linked button from the doctype that uses them (e.g. `Call
  Log` from a Lead/Contact timeline). This matches long-standing upstream ERPNext UX convention,
  not a defect introduced by this checkout.
- **Live UI reachability itself is NOT VERIFIED** (no running Desk instance — see scope note
  above). The above is a code-level judgment, not a browser-confirmed one.

## 4. Separate Frappe ecosystem apps

This repository contains **only the `erpnext` app** — no other Frappe app source is present or
vendored here, and `pyproject.toml`'s `[tool.bench.frappe-dependencies]` declares only `frappe`
(no other app is a hard dependency). Cross-checked against actual import sites in `erpnext/**/*.py`
to distinguish "integrates with, if installed" from "requires":

| App | Part of ERPNext core? | Installed in this checkout? | Required for this deployment? | Evidence |
| --- | --- | --- | --- | --- |
| **HRMS** | No — split out in `erpnext/patches/v14_0/remove_hr_and_payroll_modules.py` | Not installed | SEPARATE APP REQUIRED (only if HR/Payroll needed) | Core keeps a lightweight `Employee` doctype (`erpnext/setup/doctype/employee`) for cross-module linking only; `employee.py:377` has an `employee_holiday_list` hook explicitly meant for HRMS to override when installed. Leave/Attendance/Salary Slip/Payroll Entry/Expense Claim/Appraisal doctypes confirmed absent from this repo. |
| **Payments** | No — separate app | Not installed in this checkout's build; CI's own test fixtures (`site_config_postgres.json`) install it alongside erpnext for full test coverage | OPTIONAL (required only for Payment Request / online payment gateway features) | All 5 `from payments...` imports in `erpnext/accounts/doctype/payment_request/payment_request.py` are function-scoped, not module-level — core loads and runs fine without it; only Payment Request gateway actions would fail if actually invoked without it installed |
| **Healthcare** | No — separate app | Not installed | SEPARATE APP REQUIRED (only if healthcare vertical needed) | 2 files reference "healthcare" only in domain-name strings (`erpnext/domains/`), no functional dependency |
| **Education** | No — separate app | Not installed | SEPARATE APP REQUIRED (only if education vertical needed) | 3 files, same pattern as Healthcare |
| **Lending** | No — separate app | Not installed | SEPARATE APP REQUIRED (only if lending/loan vertical needed) | 4 files reference it in passing (domain/vertical naming), no hard import |
| **CRM (Frappe CRM)** | **Do not confuse with ERPNext's own core `CRM` module** (`erpnext/crm/` — Lead/Opportunity/Prospect, present and PASS above) | Not installed | OPTIONAL — `erpnext/crm/frappe_crm_api.py` is a one-way integration API (create Prospect/Customer/Contact from a Frappe CRM webhook), gated by `CRM Settings.enable_frappe_crm_data_synchronization` and `is_crm_installed()` checks; ERPNext's own CRM module is fully functional without it | Confirmed via `erpnext/crm/doctype/crm_settings/crm_settings.py` and the security/PostgreSQL-audit work done earlier in this session |
| **Helpdesk** | No — separate app | Not installed | OPTIONAL (ERPNext core `Support`/`Issue` module covers basic ticketing without it) | 0 references found in `erpnext/**/*.py` |
| **Insights** | No — separate app | Not installed | OPTIONAL (BI/analytics) | 0 references found |
| **Builder** | No — separate app | Not installed | OPTIONAL (website page builder) | 11 files reference it only in web-template/portal context strings, no hard dependency found |
| **Drive** | No — separate app | Not installed | OPTIONAL (file collaboration) | 3 references, no hard dependency |
| **Wiki** | No — separate app | Not installed | OPTIONAL | 1 reference, no hard dependency |

**`bench list-apps` equivalent**: **NOT VERIFIED** — no bench/site is currently running (stopped
per instruction; see scope note). Based on static inspection: this checkout would install exactly
`frappe` (fetched fresh from `develop` per the Containerfile built earlier in this session) +
`erpnext` (this checkout). No other app is bundled.

## 5. Module configuration validation

Checked `modules.txt`, `hooks.py`, `pyproject.toml`, `domains.py`, Workspace JSON, and DocType
metadata for missing entries, orphaned modules, invalid references, and broken imports.

**Method**: every `"erpnext.<dotted.path>"` string literal in `hooks.py` (115 found) was resolved
against the actual file tree + top-level names in the target file (AST-parsed, not just file
existence). 8 initially flagged as unresolvable; 6 were checker false-positives (references into
`__init__.py`, which the first pass didn't check) confirmed valid on manual review. **3 were
genuinely broken** — confirmed against the real upstream `frappe/erpnext` `develop` branch via
GitHub API (not just this checkout) to determine whether each was a fork regression or a
pre-existing upstream issue, and further confirmed via GitHub code search of `frappe/frappe`
whether the framework actually calls the hook key at all:

| Reference | hooks.py location | Upstream state | Framework consumes this hook key? | Action |
| --- | --- | --- | --- | --- |
| `erpnext.regional.france.utils.test_method` | `regional_overrides["France"]` | Identically broken upstream | Yes — consumed by erpnext's own `allow_regional` decorator (`erpnext/__init__.py`), live/reachable | **FIXED** — created `erpnext/regional/france/utils.py::test_method()` (a test-double, not real French tax logic — see rationale below) and extended `erpnext/tests/test_regional.py` to actually exercise the France dispatch path (previously only the no-override fallback was tested) |
| `erpnext.controllers.print_settings.get_print_settings` | `additional_print_settings` | Identically broken upstream | **No** — confirmed via `gh api search/code -f q="additional_print_settings repo:frappe/frappe"` → 0 results; this hook key is not read anywhere in the current Frappe framework | **Not fixed** — genuinely dead/inert configuration (zero runtime risk since nothing ever calls it), and no ground truth exists anywhere for what a `get_print_settings()` function should actually do (real print-template wiring for this app already happens via the *different*, correctly-wired `set_print_templates_for_item_table`/`set_print_templates_for_taxes` functions, called directly from `accounts_controller.py:540-541`). Fabricating a new function's behavior with no spec would be exactly the "reconstruct functionality" the task instructs against. Documented here; recommend reporting upstream. |
| `erpnext.utilities.bot.FindItemBot` | `bot_parsers` | Identically broken upstream | **No** — confirmed via the same GitHub code search method, 0 results in `frappe/frappe` | **Not fixed** — same reasoning: dead/inert (the Frappe "Bot" chat-parser feature this hooks into no longer exists in the framework), zero runtime risk, and rebuilding a `FindItemBot` NLP class from nothing would be fabricating removed functionality, which the task explicitly prohibits. Documented here; recommend reporting upstream. |

**Why the France fix was appropriate but the other two weren't**: the France entry has a
companion test file (`erpnext/tests/test_regional.py`, itself brand-new — added in the same commit
visible at the top of this shallow clone) whose entire purpose is to validate the override-dispatch
mechanism itself, with an unambiguous, spec-free correct implementation (return any distinguishable
string to prove dispatch occurred — not real French tax/regional business logic, which this audit
does not attempt to invent). The other two would require guessing at real, unknown business
behavior with zero upstream reference to work from.

**No other broken references, orphaned modules, duplicate registrations, or invalid Workspace
links were found.** `domains.py` (`distribution.py`, `manufacturing.py`, `retail.py`,
`services.py`) references only doctypes/fields confirmed present above.

## Sections 6-8: database, UI, and permission checks — NOT VERIFIED live

Per the task's own acceptance rule ("a module folder existing in Git is not sufficient... confirm
after `bench migrate`"), these require a running PostgreSQL site and Desk UI session. A live
verification run was in progress this session (Docker image built successfully from this
checkout's source — see [FORK_CHANGES.md](FORK_CHANGES.md) — and `db`/`redis`/`configurator`
services started cleanly) but was **stopped before `bench new-site`/`bench migrate` completed**, at
the user's explicit instruction, in favor of this static audit. Consequently:

- **Module Def / DocType / Workspace / Report / Dashboard / Role / Custom Field / Property Setter
  presence in the database**: NOT VERIFIED.
- **Desk UI Workspace visibility, sidebar, shortcuts, broken routes, console errors**: NOT VERIFIED.
- **Permission testing across Administrator / System Manager / functional-role / restricted user**:
  NOT VERIFIED.

These are not weaker claims dressed up — they are genuinely unproven until a site comes up. The
static findings in Sections 1–5 above (source presence, controller integrity, hook-reference
validity) are real and verified; they are a necessary but not sufficient condition for the modules
to actually work end-to-end. Re-run the Docker verification (`docker compose -f
docker-compose.local.yml --env-file .env up -d`, then `bench new-site --db-type postgres ...` and
`bench migrate` — see [DEPLOYMENT.md](DEPLOYMENT.md)) to close this gap.

## 9. Removed/disabled functionality

No functionality was found deliberately deleted, commented out, or hidden by this fork — `git
status`/`git diff` at the start of this audit showed no modifications to Workspace JSON, hooks.py
module wiring, or permission definitions prior to the fixes listed above and in
[FORK_CHANGES.md](FORK_CHANGES.md). The three hook-reference issues in Section 5 predate this
fork (confirmed identical upstream) — they were not "removed by a previous modification" to this
checkout, they are inherited upstream state.

## 10. Installed applications

**NOT VERIFIED via `bench list-apps`** (no live bench — see scope note). Static equivalent: this
checkout's `Containerfile` (built successfully earlier this session) installs exactly `frappe`
(develop branch, fetched fresh) and `erpnext` (this checkout's local source). No other app.

## 11. Core business flow DocType cross-check

Every DocType named in the task's Sales/Purchasing/Inventory/Manufacturing/Accounting/Projects/
Assets flow diagrams was individually looked up by its DocType JSON `name` field (not guessed from
folder names) — **all present, 0 missing**:

- **Sales**: Lead, Opportunity, Quotation, Sales Order, Delivery Note, Sales Invoice, Payment Entry — all found.
- **Purchasing**: Supplier, Material Request, Request for Quotation, Supplier Quotation, Purchase Order, Purchase Receipt, Purchase Invoice, Payment Entry — all found.
- **Inventory**: Item, Warehouse, Stock Entry, Stock Reconciliation, Stock Ledger Entry — all found.
- **Manufacturing**: BOM, Production Plan, Work Order, Job Card — all found.
- **Accounting**: Chart of Accounts Importer, Journal Entry, GL Entry, Period Closing Voucher, plus reports Trial Balance, Profit and Loss Statement, Balance Sheet, General Ledger, Accounts Receivable, Accounts Payable — all found.
- **Projects**: Project, Task, Timesheet — all found.
- **Assets**: Asset, Asset Depreciation Schedule, Asset Movement, Asset Capitalization — all found.

Whether these DocTypes actually *execute* correctly end-to-end (submit a real Sales Order, post
real GL entries, etc.) is a runtime/workflow question, not a presence question — see
[TEST_REPORT.md](TEST_REPORT.md) for what could and couldn't be exercised live this session.

## 12. HRMS vs. ERPNext core — explicit statement

**SEPARATE APP REQUIRED.** HRMS (leave, attendance, payroll, appraisal) is not part of this
ERPNext version's core and is not installed in this checkout. This is intentional upstream
behavior (`erpnext/patches/v14_0/remove_hr_and_payroll_modules.py`), not a defect. See Section 4
table above for the compatible app (`frappe/hrms`) and its optional/required status.

## 13. Fixes applied

1. **`erpnext/regional/france/utils.py`** (new file) + **`erpnext/tests/test_regional.py`**
   (extended) — see Section 5. Also fixed a latent test-hygiene issue while touching this file:
   the existing `test_regional_overrides` test set `frappe.flags.country` without resetting it,
   which could leak into later tests in the same worker process; added
   `self.addCleanup(frappe.flags.pop, "country", None)` to both tests.

No other legitimate problems requiring a fix were found in this audit's scope. The two other
broken hook references (Section 5) were deliberately **not** fixed, with reasoning documented
above — fabricating unknown behavior for dead, unconsumed configuration was judged worse than
leaving well-documented dead code in place, consistent with this fork's stated goal of staying
close to upstream and not reconstructing removed/never-implemented functionality.

## Method and limitations

- This is a **shallow git clone** (`.git/shallow` present, depth 1) — only one commit is visible
  locally. Claims like "added in the same commit" refer to what's visible in this shallow clone,
  not necessarily true upstream authorship history. Where deeper certainty was needed (was a
  reference *always* broken, or fork-introduced?), this audit fetched the real
  `frappe/erpnext`/`frappe/frappe` `develop` branches from GitHub directly via the `gh` CLI rather
  than relying on local git history.
- Doctype/report/workspace counts were produced by walking the actual file tree and parsing JSON
  (`os.walk` + `json.load`), not by trusting directory names or running an approximate `find |
  wc -l` on folder names alone.
- "Controller present" means a `.py` file with the matching name exists next to the DocType JSON —
  it does not mean the controller's logic is bug-free (see [TECHNICAL_AUDIT.md](TECHNICAL_AUDIT.md)
  and [POSTGRESQL_COMPATIBILITY.md](POSTGRESQL_COMPATIBILITY.md) for deeper code-correctness work
  done earlier this session).

---

## Summary

1. **Total expected ERPNext modules**: 21
2. **Total found (source present)**: 21
3. **Total fully working (source + DB + UI + permissions + functional test all verified)**: **0
   can be claimed at that full standard** — DB/UI/permission verification was not completed live
   this session (stopped per instruction). All 21 passed every check that *is* verifiable
   statically (source, controllers, no broken imports, hook-reference validity).
4. **Total broken**: 0 modules broken at the source/registration level. 2 dead/inert
   hook-configuration references found (both confirmed pre-existing upstream, zero runtime risk).
5. **Total fixed**: 1 (regional override dispatch gap + its test coverage)
6. **Separate apps required**: HRMS, Healthcare, Education, Lending (if those verticals are
   needed for this deployment — none currently required by anything in this checkout)
7. **Optional apps available (not required, integrate if installed)**: Payments, Frappe CRM,
   Helpdesk, Insights, Builder, Drive, Wiki
8. **Missing Workspaces**: 0 confirmed missing — 9 modules have no dedicated top-level Workspace
   by design (utility/settings/log doctypes), matching stock upstream ERPNext UX; live
   reachability itself NOT VERIFIED
9. **Missing DocTypes**: 0 (across all 21 modules and all business-flow cross-checks in Section 11)
10. **Broken routes**: NOT VERIFIED (no live Desk session)
11. **Permission-related issues**: 3 DocTypes ship with an empty `permissions` array
    (`Authorization Control`, `Import Supplier Invoice`, `UAE VAT Settings`) — confirmed
    byte-for-byte identical to upstream `frappe/erpnext` `develop`, not a fork issue; not modified
    without further evidence of intended behavior. Live permission testing across roles NOT VERIFIED.
12. **Remaining blockers**: completing the live Docker verification (site creation → migrate →
    Desk UI walkthrough → role-based permission testing) that was stopped mid-run this session —
    see [TEST_REPORT.md](TEST_REPORT.md) and [DEPLOYMENT.md](DEPLOYMENT.md) for the exact commands
    to resume it.

## Final result

**MODULE AUDIT HAS OUTSTANDING ISSUES**

Reasoning: source-code-level presence, registration, and integrity are fully verified and clean
(21/21 modules, 532/532 controllers, 0 broken imports, 1 genuine broken reference found and fixed,
2 pre-existing-upstream dead references documented). However, per this audit's own Section 15
acceptance rule, a module cannot be marked fully PASS without database + UI + permission +
functional verification, and that live verification was not completed this session (stopped
before `bench new-site` finished, at explicit user instruction, to prioritize this static audit).
The outstanding issue is exclusively "live verification not yet run" — not any known code defect.
