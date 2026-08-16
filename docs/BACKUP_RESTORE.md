# Backup and Restore (PostgreSQL)

Date: 2026-08-12

Status of the procedures below is recorded per-step. See
[TEST_REPORT.md](TEST_REPORT.md) for what was actually executed on this machine versus what is
documented but **NOT VERIFIED** by an actual run.

All commands assume the local Docker Compose stack (`docker-compose.local.yml`) with site name
`frontend` (the default in `.env.example`). Substitute your real site name and container/bench
paths for a non-Docker bench install — the underlying `bench backup`/`bench restore` commands are
identical either way; only how you get a shell matters.

## What a Frappe/ERPNext backup actually contains

`bench --site <site> backup` produces, under
`sites/<site>/private/backups/` (inside the bench — this is the `sites` volume in the Docker
stack):

1. **Database dump** — `<timestamp>-<site>-database.sql.gz` (PostgreSQL: a `pg_dump` custom-format
   or plain-SQL dump depending on Frappe version; the same `bench restore` command handles it
   either way — do not hand-invoke `pg_restore`/`psql` unless you know exactly which format your
   Frappe version wrote).
2. **Site config** — `<timestamp>-<site>-site_config_backup.json`. Contains `db_name`, `db_type`,
   and — critically — the site's `encryption_key`. **Losing this file makes every encrypted field
   in the database (Email Account passwords, Payment Gateway secrets, any `Password`-fieldtype
   value) permanently unrecoverable**, even though the raw ciphertext is still in the SQL dump.
   Treat it as a secret with the same sensitivity as the database dump itself.
3. **Public files** — `<timestamp>-<site>-files.tar` (only with `--with-files`).
4. **Private files** — `<timestamp>-<site>-private-files.tar` (only with `--with-files`).

## Taking a backup

```sh
# Inside the backend container (docker compose exec) or on a bare-metal bench:
bench --site frontend backup --with-files

# Compress-and-verify in one step (recommended for anything you'll actually rely on):
bench --site frontend backup --with-files --compress
```

Via the local Docker stack:

```sh
docker compose -f docker-compose.local.yml exec backend bench --site frontend backup --with-files
# Copy the backup set out of the named `sites` volume to the host BACKUP_PATH (see .env.example):
docker compose -f docker-compose.local.yml cp \
  backend:/home/frappe/frappe-bench/sites/frontend/private/backups/. "${BACKUP_PATH:-./backups}/"
```

**Off-host copy is mandatory for anything that counts as a real backup.** A backup that lives only
on the same disk/volume as the production database survives neither disk failure nor the
compromise scenario ransomware/accidental `docker volume rm` represents. Ship the three files
above (`*-database.sql.gz`, `*-site_config_backup.json`, `*-files.tar`,
`*-private-files.tar`) to S3-compatible remote storage — the `BACKUP_S3_*` variables in
`.env.example` are the placeholders for that; wiring an actual `restic`/`rclone` push (the
production Containerfile already includes `restic`) is a **production deployment task**, not
something this local dev stack does automatically.

## Automating backups (production)

Frappe's own scheduler already runs a daily backup job by default
(`hooks.py: scheduler_events` in the Frappe framework, not ERPNext) once
`backup_frequency`/`backup_limit` site config is set — this only writes to local disk under
`sites/<site>/private/backups/`, so it does **not** by itself satisfy "off-host backup." For
production, additionally cron a script that runs `bench backup --with-files` and immediately
pushes the resulting files to remote storage, then prunes local copies older than your retention
window. Document the exact schedule/retention you choose in your own deployment runbook — this
audit does not invent a retention policy on your behalf.

## Restoring a backup

**Restore only into a throwaway/test site or a deliberately-being-recovered production site —
`bench restore` drops and recreates the target database.**

```sh
# 1. Create (or reuse) a fresh site to restore into:
bench new-site restored-test --db-type postgres --db-host db \
  --db-root-username postgres --db-root-password "$POSTGRES_PASSWORD" \
  --admin-password "$ADMIN_PASSWORD" --no-mariadb-socket

# 2. Restore the database dump + site_config (encryption key) + files:
bench --site restored-test restore \
  /path/to/<timestamp>-frontend-database.sql.gz \
  --with-public-files /path/to/<timestamp>-frontend-files.tar \
  --with-private-files /path/to/<timestamp>-frontend-private-files.tar \
  --db-type postgres

# 3. If the site_config_backup.json's encryption_key differs from a fresh site's auto-generated
#    one, restore it explicitly (`bench restore` does this automatically when the backup file
#    naming convention is intact — verify with `bench --site restored-test console` ->
#    `frappe.conf.encryption_key` matches the value in the *-site_config_backup.json).

# 4. Always migrate after restore, in case the backup predates schema changes already applied to
#    the bench's installed app code:
bench --site restored-test migrate
```

## Verifying a restore actually worked

A backup is not valid until this has been done — do not treat "the restore command exited 0" as
proof:

1. Log in to the restored site as Administrator.
2. Spot-check that record counts look right for a known doctype (`bench --site restored-test
   console` → `frappe.db.count("Sales Invoice")` compared against what you expect from the source
   site at backup time).
3. Open a specific document you know existed (e.g. a recent Sales Invoice) and confirm its data,
   including child table rows, is intact.
4. Confirm at least one encrypted field (an Email Account password, if configured) still decrypts
   correctly — proves the `encryption_key` restore step worked.
5. Run `bench --site restored-test doctor` (checks basic site health) and review its output.

## Encryption key handling

- The site's `encryption_key` (in `site_config.json`) is generated once at `bench new-site` time
  and never changes automatically. It is backed up in `*-site_config_backup.json` alongside every
  `bench backup` run.
- **Never** commit `site_config.json` or any `*-site_config_backup.json` to version control — both
  contain this key plus the site's live DB credentials. They are already outside this repo (they
  live in the bench's `sites/` directory, which `docker-compose.local.yml` keeps in a Docker
  volume, not a repo-tracked path).
- Store the encryption key backup with at least the same access control as your database
  credentials — anyone with both the SQL dump and the encryption key can decrypt every secret
  field in the database.
