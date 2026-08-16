# ERPNext Deployment Guide (PostgreSQL)

This guide covers deploying this fork to a Linux server using the Docker architecture in this
repository (`Containerfile` + `docker-compose.local.yml`, adapted from the official
[frappe_docker](https://github.com/frappe/frappe_docker) production image layout). It targets a
plain Linux VM/container host — nothing here is cloud-provider-specific.

**Read this first**: `docker-compose.local.yml` is documented and tested as a **local
development/test** stack (see [docs/TEST_REPORT.md](docs/TEST_REPORT.md) for exactly what was
verified on this machine and what was not). Before using it in production, apply the hardening
in [Production hardening](#production-hardening) below — do not `docker compose up` this file
as-is against real customer data.

---

## 1. Provision a Linux server

Any modern Linux distribution with Docker support. Minimum for a small ERPNext install: 2 vCPU,
4 GB RAM, 40 GB disk (PostgreSQL + Redis + bench assets + backups grow this over time — monitor
disk usage). Open only the ports you actually need externally (80/443 for the reverse proxy;
nothing else needs to be internet-facing).

## 2. Install prerequisites

```sh
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
docker compose version   # confirm Compose v2 (bundled with modern Docker)
```

## 3. Configure DNS

Point an A/AAAA record for your domain at the server's public IP before requesting a TLS
certificate (step 15 needs this to resolve).

## 4. Clone the repository

```sh
git clone <this-fork's-url> erpnext
cd erpnext
```

## 5. Configure environment

```sh
cp .env.example .env
# Edit .env: set real POSTGRES_PASSWORD, ADMIN_PASSWORD, DOMAIN, LETSENCRYPT_EMAIL, SMTP
# credentials if you have them yet. See .env.example for every variable and its category.
chmod 600 .env
```

**Never commit `.env`.** It's already in `.gitignore`; double-check with `git status` before any
commit in this directory.

## 6–7. Start PostgreSQL + Redis / 8. Build ERPNext

These three happen together via Compose:

```sh
docker compose -f docker-compose.local.yml --env-file .env build backend
docker compose -f docker-compose.local.yml --env-file .env up -d db redis-cache redis-queue
```

The `build` step compiles a bench from **this repository's actual source** (see `Containerfile`)
— not a prebuilt upstream image — so any fork-specific fix is included. Expect this to take
15–40 minutes on first build (Node/wkhtmltopdf/Chromium install, `bench init`, asset build); it is
cached on subsequent builds unless dependencies change.

## 9. Create the PostgreSQL-backed site

```sh
docker compose -f docker-compose.local.yml --env-file .env up -d configurator
docker compose -f docker-compose.local.yml --env-file .env up create-site
```

This runs (inside the `create-site` container, using your `.env` values):

```sh
bench new-site --db-type postgres --db-host db --db-name "$POSTGRES_DB" \
  --db-password "$POSTGRES_PASSWORD" --db-root-username "$POSTGRES_USER" \
  --db-root-password "$POSTGRES_PASSWORD" --admin-password "$ADMIN_PASSWORD" \
  --install-app erpnext --set-default "$SITE_NAME"
```

## 10. Install ERPNext

Already done by `--install-app erpnext` above — `create-site` both creates the site and installs
the app in one step, matching how `bench new-site` is documented to work.

## 11. Run migrations

Already current immediately after `new-site` (it installs the latest schema directly). For any
**subsequent** deployment (updating an existing site — see [Updating ERPNext](#updating-erpnext)
below), migrations are a required, separate step:

```sh
docker compose -f docker-compose.local.yml --env-file .env exec backend \
  bench --site "$SITE_NAME" migrate
```

## 12. Build assets

Already baked into the image by the `Containerfile`'s `bench build` step — no separate action
needed for a fresh deploy. Re-run the `build` step (step 8) after any source change.

## 13. Start application services

```sh
docker compose -f docker-compose.local.yml --env-file .env up -d
```

This starts (or leaves running) all services: `backend` (gunicorn), `frontend` (nginx), `websocket`
(Socket.IO), `queue-short`/`queue-long` (background workers), `scheduler`.

## 14–15. Configure reverse proxy / enable HTTPS

`docker-compose.local.yml`'s `frontend` service is nginx, but it terminates plain HTTP on 8080 and
is published directly to the host — fine for local testing, **not sufficient for production TLS**.
For production, put a TLS-terminating reverse proxy in front of it. Two supported options,
consistent with the "don't invent an incompatible topology" instruction: either (a) adopt
frappe_docker's own Traefik-based `overrides/compose.https.yaml` mechanism (see the
[frappe_docker docs](https://github.com/frappe/frappe_docker) for the exact compose overlay,
since this repo does not vendor Traefik configuration), or (b) run your own nginx/Caddy in front
of this stack's `frontend:8080`, obtaining a certificate via `certbot`/ACME for `$DOMAIN` and
`$LETSENCRYPT_EMAIL` from `.env`, and forwarding:

- HTTP → HTTPS redirect on 80.
- HTTPS on 443, `proxy_pass` to `frontend:8080`.
- `Upgrade`/`Connection: upgrade` headers preserved for `/socket.io` (websocket upgrade) —
  `frontend`'s own nginx config already proxies `/socket.io` correctly to the `websocket` service;
  your outer proxy just needs to not strip the upgrade headers.
- A request-size limit matching or exceeding `CLIENT_MAX_BODY_SIZE` in `.env` (default `50m`).
- `proxy_read_timeout` at least `PROXY_READ_TIMEOUT` (default 120s) so long report/print-format
  requests don't get cut off.

## 16. Verify workers

```sh
docker compose -f docker-compose.local.yml --env-file .env ps queue-short queue-long
docker compose -f docker-compose.local.yml --env-file .env logs --tail=50 queue-short
```
Confirm no crash-looping (repeated restarts). Enqueue a real background job (e.g. trigger a bulk
export from the UI) and confirm it completes.

## 17. Verify scheduler

```sh
docker compose -f docker-compose.local.yml --env-file .env logs --tail=50 scheduler
docker compose -f docker-compose.local.yml --env-file .env exec backend \
  bench --site "$SITE_NAME" doctor
```

## 18. Verify realtime

Log in to the UI and confirm the connection indicator shows connected (no repeated
reconnect/toast errors); open two browser sessions and confirm an update in one (e.g. a comment)
appears live in the other without a page refresh.

## 19. Verify email

Configure an Email Account (Settings → Email Account) with real or a local test SMTP
(e.g. Mailhog/Mailpit for a smoke test — not included in this repo's compose file; add it as a
service if you want automated verification) and send a test email from the UI. Do **not** put
production SMTP credentials in `.env` in this repository's working copy if you can help it —
prefer setting them directly via the Email Account doctype in the running site.

## 20. Configure backups

See [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md) — set `BACKUP_S3_*` in `.env` and wire a cron
job (or the production Containerfile's bundled `restic`) to push `bench backup --with-files`
output off-host on a schedule. Not automated by this repo's compose file — a scheduled backup
push is a deployment-specific operational task, not something safe to assume a default for.

## 21. Run smoke tests

```sh
curl -sf http://localhost:${HTTP_PUBLISH_PORT:-8080}/api/method/ping
# Expect: {"message":"pong"}
```
Then log in as Administrator through the browser and walk one representative workflow (e.g. create
a Customer → Sales Order) end to end.

---

## Updating ERPNext

```sh
git pull                                    # or checkout the target commit/tag
docker compose -f docker-compose.local.yml --env-file .env build backend
docker compose -f docker-compose.local.yml --env-file .env up -d --no-deps backend frontend \
  websocket queue-short queue-long scheduler
docker compose -f docker-compose.local.yml --env-file .env exec backend \
  bench --site "$SITE_NAME" migrate
```

Take a backup (see below) **before** every update that changes the app version — migrations can
include irreversible schema/data changes.

## Applying migrations

```sh
docker compose -f docker-compose.local.yml --env-file .env exec backend \
  bench --site "$SITE_NAME" migrate
```
`bench migrate` is idempotent — safe to re-run. Watch its output for patch failures; a failed
patch typically needs investigation before retrying (do not blindly re-run in a loop).

## Rolling back a failed deployment

1. Stop application services (leave `db`/`redis-*` running): `docker compose -f
   docker-compose.local.yml --env-file .env stop backend frontend websocket queue-short
   queue-long scheduler`.
2. Restore the pre-deployment database backup (see
   [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md)) — **required** if the failed deployment ran
   any migration, since app code and schema must stay in lockstep with Frappe/ERPNext.
3. Check out the previous working commit/tag: `git checkout <previous-ref>`.
4. Rebuild and restart: `docker compose -f docker-compose.local.yml --env-file .env build backend
   && docker compose -f docker-compose.local.yml --env-file .env up -d`.
5. Re-run the smoke test (step 21 above) before declaring the rollback complete.

## Backup / Restore

See [docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md) for the full procedure, including how to
**verify** a restore actually worked (not just that the command exited 0).

## Troubleshooting

| Symptom | Where to look |
|---|---|
| Site won't load, 502/504 from proxy | `docker compose logs backend frontend`; confirm `backend` health check is passing (`docker compose ps`) |
| Background jobs never complete | `docker compose logs queue-short queue-long redis-queue`; confirm Redis is reachable from workers |
| Scheduled jobs (reports, reminders) not firing | `docker compose logs scheduler`; confirm the `scheduler` container is running, not crash-looping |
| Realtime/websocket not connecting | Browser console for the `/socket.io` request; `docker compose logs websocket`; confirm your reverse proxy forwards `Upgrade`/`Connection` headers |
| `bench migrate` fails | Read the specific patch name in the traceback; check `erpnext/patches.txt` / the failing patch's own code before retrying — do not skip patches to force success |
| Emails not sending | Email Account doctype's own "Test" button in the UI first (isolates SMTP config from app bugs); then `docker compose logs backend` for a full traceback |
| PostgreSQL connection errors | `docker compose logs db`; confirm `POSTGRES_PASSWORD` in `.env` matches what the site was created with (changing it after `new-site` requires updating `site_config.json`, not just `.env`) |

---

## Production hardening

Applied on top of the base stack described above, before this is a real production deployment:

- **Secrets**: never rely on `.env` sitting on disk in plaintext for very sensitive deployments —
  use your platform's secret manager (Docker Swarm secrets, systemd credentials, Vault, etc.) and
  inject at container start instead. At minimum, `chmod 600 .env` and restrict the deploying
  user's access to the host.
- **TLS**: mandatory — see step 14–15 above.
- **PostgreSQL**: do not publish port 5432/`POSTGRES_HOST_PORT` to the host in production (remove
  the `ports:` mapping under the `db` service) — the app containers reach it over the internal
  `frappe_network` regardless. Set a connection limit appropriate to `GUNICORN_WORKERS ×
  GUNICORN_THREADS` plus worker/scheduler connections. Enable regular automated backups (see
  above) with off-host storage.
- **Redis**: add `requirepass` and update `REDIS_CACHE`/`REDIS_QUEUE` accordingly if Redis is ever
  reachable outside a fully private network.
- **Resource limits**: add `deploy.resources.limits` (or plain `mem_limit`/`cpus` for non-Swarm
  Compose) to each service sized to your server, so one runaway report query can't starve the
  whole host.
- **Log retention**: container stdout/stderr (see [Observability](#observability) below) should
  be shipped to a log aggregator or at minimum bounded with Docker's `json-file` log rotation
  options (`max-size`, `max-file`) — unbounded container logs will eventually fill the disk.
- **Non-root**: the Containerfile already runs the app as the `frappe` user (not root) — confirm
  this is preserved if you customize the image further.

## Observability

| Component | Where logs land |
|---|---|
| Application (gunicorn/backend) | `docker compose logs backend`; also `sites/logs/` in the `logs` volume |
| Web server (nginx/frontend) | `docker compose logs frontend`; nginx access/error logs are symlinked to stdout/stderr inside the image |
| Workers | `docker compose logs queue-short queue-long` |
| Scheduler | `docker compose logs scheduler` |
| Realtime | `docker compose logs websocket` |
| PostgreSQL | `docker compose logs db` |
| Redis | `docker compose logs redis-cache redis-queue` |

None of these log secrets/passwords by default — do not add custom logging that prints
`site_config.json`, `.env`, or request bodies containing credentials.
