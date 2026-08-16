# Security Review

Date: 2026-08-12

**Scope**: `erpnext/` application code only. Core authentication, session management, password
hashing/reset, the DocType permission engine, CSRF protection, and CORS machinery all live in the
Frappe framework (a separate upstream project, not in this repository) — this review covers what
ERPNext's own code does with/on top of that framework, not the framework itself.

## Method

Targeted static review (grep + manual read of matches, not an automated scanner) across seven
categories: SQL injection, command injection, path traversal/unrestricted file access, whitelisted
methods with weak/missing permission checks, hardcoded secrets, insecure deserialization, and
CORS/debug configuration. See [TEST_REPORT.md](TEST_REPORT.md) for what could and could not be
verified dynamically (no live instance was available to attempt actual exploit requests against a
running site at the time this was written — everything below is a code-level finding, not a
penetration-test result).

## Finding: XPath injection in genericode Code List import — **FIXED**

**File**: `erpnext/edi/doctype/common_code/common_code.py`, `import_genericode()`
**Severity**: Low (reachable only by an authenticated user with read access to the specific
uploaded genericode File and permission to trigger a Code List import; impact is a filter bypass
within data the caller can already read, not cross-user data exposure or code execution).

**Before**:
```python
xpath_expr = ".//SimpleCodeList/Row"
filter_conditions = [
    f"Value[@ColumnRef='{column_ref}']/SimpleValue='{value}'"
    for column_ref, value in (filters or {}).items()
]
```
`filters` is a `dict` argument on the whitelisted `process_genericode_import()` API
(`erpnext/edi/doctype/code_list/code_list_import.py`), parsed straight from
`frappe.parse_json(filters)` with no escaping before being string-interpolated into an XPath
expression.

**Concrete exploit, verified locally with a standalone lxml reproduction** (not part of the
committed test suite, run in a throwaway venv): a filter value of `Group 1' or '1'='1` turns the
intended predicate `Value[@ColumnRef='category']/SimpleValue='Group 1' or '1'='1'` into an
always-true condition, so **every** row in the genericode file imports as a Common Code —
including rows the caller's filter was specifically meant to exclude. The vulnerable version
matched all rows for this payload; the fixed version matches none (the literal string never equals
any real `SimpleValue`).

**Fix**: bind `column_ref`/`value` as lxml XPath variables (`$colN`/`$valN`, resolved via
`root.xpath(xpath_expr, **xpath_variables)`) instead of interpolating them into the expression
string — the standard parameterization mechanism for XPath via lxml, equivalent in spirit to a
parameterized SQL query.

**Regression tests added**: `erpnext/edi/doctype/code_list/test_code_list_import.py` —
`test_process_genericode_import_applies_filters` (legitimate filter still works, still returns
exactly the expected rows) and `test_process_genericode_import_filter_value_is_not_xpath_injectable`
(the exact payload above now imports zero rows instead of bypassing the filter).
**NOT VERIFIED by execution in the ERPNext test runner** — the standalone lxml reproduction above
confirmed the underlying mechanism, but no local bench/site was available to run
`bench run-tests` against the committed test file itself at the time this document was written;
see [TEST_REPORT.md](TEST_REPORT.md) for whether that gap was later closed once a live environment
came up. Both tests compile and pass the project's static checks.

## Categories reviewed — no significant findings

- **SQL injection**: `erpnext/**/report/**/*.py` (the highest-risk surface for this class of bug)
  and a repository-wide sweep for `frappe.db.sql()` combined with f-strings/`.format()`/`%`
  formatting. Dynamic SQL fragments built via string interpolation only ever splice in
  *column/field names* sourced from trusted metadata (Accounting Dimension definitions, static
  literals) — actual values consistently go through `%(name)s`-style parameterized placeholders or
  the query builder. No case found where a value reachable from a non-trusted user reaches a query
  string unparameterized.
- **Command injection**: no `subprocess`, `os.system`, `os.popen`, or `shell=True` usage anywhere
  in `erpnext/`.
- **Path traversal / unrestricted file access**: file-upload/import code
  (`chart_of_accounts_importer.py`, `bank_statement_import.py`, `bank_transaction_upload.py`,
  `code_list_import.py`, `rename_tool.py`, `financial_report_template.py`) resolves all
  user-supplied files through Frappe's `File` doctype (`check_permission("read")` +
  `get_full_path()`), which enforces both permission checks and safe path resolution — no raw
  attacker-controlled path string reaches `open()`. `code_list_import.py`'s remote-URL import path
  additionally allowlists local-file URL prefixes (`/files/`, `/private/files/`), which is the SSRF
  guard already covered by this project's own existing tests
  (`test_import_genericode_rejects_remote_file_url`, `test_import_genericode_rejects_file_scheme_url`).
- **Whitelisted methods with weak/missing permission checks**: enumerated every
  `@frappe.whitelist(allow_guest=True)` method and a broad sample of plain `@frappe.whitelist()`
  methods. Guest-facing endpoints are consistently gated by a feature-enable flag, rate limiting
  (`@rate_limit`), scoping to already-public content (published Help Articles), or a signed,
  hashed, time-limited verification token for the one case that inserts as a synthetic user
  (appointment-booking verification flow). Destructive bulk operations
  (`Transaction Deletion Record`) consistently check `frappe.only_for("System Manager")`. No
  `frappe.get_all()` call bypassing user-permission filters was found exposed to guests.
- **Hardcoded secrets/credentials**: no API keys, passwords, or tokens found committed in
  `erpnext/**/*.py`, fixture JSON, or config files.
- **Insecure deserialization**: no `pickle.loads` or unsafe `yaml.load()` anywhere in `erpnext/`.
  All dynamic-expression evaluation goes through Frappe's sandboxed `frappe.safe_eval()`
  (used for admin-authored SLA/pricing-rule/financial-report formulas) — the framework-sanctioned
  safe pattern, not raw `eval()`/`exec()` on request data. `ast.literal_eval()` usage in
  `financial_report_engine.py` only parses literal Python structures, no code-execution risk by
  design.
- **CORS / debug-mode configuration**: `erpnext/hooks.py` sets neither — confirmed this is
  entirely Frappe-framework/`site_config.json` responsibility, as expected for an app layer. Not
  a gap in this repo; flagging it as intentionally out of scope rather than skipped.

## Authentication / authorization — what could and couldn't be verified

Per the task's requirement to test at least Administrator, System Manager, a normal ERP user, a
restricted user, and guest access: see [TEST_REPORT.md](TEST_REPORT.md) for whether a live site
came up during this audit and, if so, what was actually exercised there. The findings above are
code-level (what the whitelisted methods and permission checks *say* they do); they are not a
substitute for actually logging in as each role and probing restricted endpoints on a running
site — treat TEST_REPORT.md's live-verification section as the authoritative statement of what was
dynamically tested, and this document as static code review only.

## Dependency vulnerabilities

**NOT VERIFIED** — auditing third-party dependency CVEs (`pip-audit`/`safety` for
`pyproject.toml`'s pinned packages, `yarn audit` for `banking/`'s JS dependencies) requires a
working Python/Node environment with the actual dependency tree resolved. Not attempted in this
review; flagged as follow-up work in [TEST_REPORT.md](TEST_REPORT.md).

## Recommendations

1. Land the XPath injection fix (done in this audit).
2. Add `pip-audit`/`yarn audit` (or equivalent) to CI if not already present — not found in
   `.github/workflows/` during this audit.
3. Treat every "NOT VERIFIED" item above as open follow-up work, not as passed — see
   [TEST_REPORT.md](TEST_REPORT.md) for the authoritative PASS/FAIL/BLOCKED/NOT VERIFIED status of
   every item in this document.
