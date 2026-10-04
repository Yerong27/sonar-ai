# Demo and live operation

Sonar retains one dashboard and its full backend, migrations, Docker stack, Terraform roots, and workflows. Only the selected data source changes. The public Sites URL stays the same.

## Current operating mode

- Public frontend: `NEXT_PUBLIC_SONAR_MODE=demo`.
- Snapshot: real read-only production responses captured 4 October 2026.
- No backend calls or refresh timer in demo; interactive filters, charts, story links and investigations remain available.
- GitHub variable `SONAR_LIVE_ENABLED=false`. Deployment and Terraform workflows are disabled while the GCP stack is offline; their source is retained and independently gated by this variable.
- Local `docker compose` remains a live-development stack. Its frontend explicitly builds with live mode and the local API URL. The standalone frontend defaults to demo.

## Build or preview either mode

From `frontend`:

```bash
npm run dev:demo
npm run build:demo
# Requires a running API:
NEXT_PUBLIC_SONAR_API_BASE=http://127.0.0.1:8060 npm run dev:live
NEXT_PUBLIC_SONAR_API_BASE=https://YOUR_API npm run build:live
npm run test:demo
```

These are build-time settings. Changing a Sites runtime variable after deployment does not rebuild the browser bundle. Do not add a visitor-facing switch that requests an offline cloud API.

To deliberately replace the snapshot, first bring up a live API, then run:

```bash
node scripts/capture-demo.mjs https://YOUR_API
```

This is an operator-only read of the existing endpoints; it does not invoke the collector or Gemini. Review the generated public data before committing. Never commit the SQL export, Terraform state, database password, or provider keys.

## Offline backup and restore

Before cloud deletion, the operator must keep an SQL export, a successful local restore report with per-table counts and SHA-256, resource configuration, Terraform state, and runtime secret values in a private location outside Git. Keep an additional secure copy on another disk before deleting the local backup. The dashboard JSON is a display snapshot, **not** a database backup.

The 4 October shutdown backup is stored locally outside the repository, under `../Sonar-backups/2026-10-04/`. Its `verification.json` records the restore test. It contains sensitive production data and keys; do not publish it.

Use PostgreSQL 16 or newer to restore the gzip SQL export into a new empty database. For local PostgreSQL, the Cloud SQL ACL role `cloudsqlsuperuser` needs a `NOLOGIN` placeholder before import. Our isolated restore verification script demonstrates this without modifying the original archive:

```bash
python scripts/verify-sonar-backup.py /PRIVATE/PATH/sonar.sql.gz \
  --container sonar-backup-verify-YOUR_ID
```

The explicitly named verification container must be isolated and disposable: the script recreates its `sonar` database. Do not point it at an existing development or production container. Runtime passwords and provider credentials are not supplied by the SQL export; recover or rotate them separately.

## Restore the live GCP architecture

Restoring live cloud operation is an explicit decision to resume billing, not part of switching to demo.

1. Recreate the GCS state bucket from the bootstrap definitions if it was removed. Recover the privately archived state to the correct `bootstrap/default.tfstate` and `application/default.tfstate` objects; do not initialize an unrelated empty state over surviving IAM resources.
2. Run reviewed Terraform plans against the retained roots. Refresh reconciles manually removed resources; apply only the expected recreation plan. Restore Secret Manager values securely, never via Git. Keep Scheduler paused.
3. Rebuild the application image in Artifact Registry. Recreate Cloud SQL and import the verified SQL export into the application database; apply any later Alembic migrations after restoring existing data.
4. Restore API, migration and collector workloads, then verify `/health/ready`, `/api/status`, and `/api/runtime`.
5. Build and publish the same frontend with explicit live mode and the new API URL. Verify live requests and runtime metadata.
6. Only then enable Scheduler and the GitHub workflows, and set `SONAR_LIVE_ENABLED=true` if automated cloud deployments are wanted.

```bash
gh workflow enable deploy.yml --repo Yerong27/sonar-ai
gh workflow enable terraform.yml --repo Yerong27/sonar-ai
gh variable set SONAR_LIVE_ENABLED --body true --repo Yerong27/sonar-ai
```

The shared billing account and all Lyrebird resources are outside Sonar shutdown scope. Historical GCP costs can still appear later on the bill; an offline demo does not erase past usage.
