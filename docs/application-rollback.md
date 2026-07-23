# Application rollback runbook

Use an application rollback when a newly deployed API or collector image is unhealthy. Do not treat it as a database-schema rollback.

## Inputs

Open the failed or most recent `Deploy application` workflow summary and copy:

- previous API revision;
- previous API image;
- previous collector image;
- current API URL.

Confirm the active account and project before changing traffic:

```bash
gcloud auth list --filter=status:ACTIVE
gcloud config set project sonar-ai-prod
```

## Roll back API traffic

Set the previous revision name from the workflow summary without adding spaces or quotes to the value:

```bash
PREVIOUS_API_REVISION='replace-with-recorded-revision'

gcloud run services update-traffic sonar-api \
  --region=australia-southeast1 \
  --to-revisions="${PREVIOUS_API_REVISION}=100"
```

Verify both health and application data:

```bash
API_URL='https://sonar-api-4akcp3ehqa-ts.a.run.app'
curl -fsS "${API_URL}/health/ready"
curl -fsS "${API_URL}/api/status" | python -m json.tool
```

## Roll back the collector image

Use the immutable previous collector image from the same workflow summary:

```bash
PREVIOUS_COLLECTOR_IMAGE='replace-with-recorded-image-at-sha256'

gcloud run jobs update sonar-collector \
  --region=australia-southeast1 \
  --image="${PREVIOUS_COLLECTOR_IMAGE}"
```

Do not execute the collector merely to prove the update worked. First inspect the job configuration and decide whether an extra collection run is appropriate. The six-hour Scheduler will otherwise use the restored image at its next execution.

## Database boundary

Rolling API traffic back or restoring the collector image does not change the Cloud SQL schema. The earlier migration may already be committed and may be required by data written after deployment. Never run `alembic downgrade` automatically.

If the previous application image cannot operate with the current schema:

1. stop and assess the migration and affected data;
2. prefer a forward application fix or a forward schema migration;
3. restore a database backup only as a separately approved recovery operation with an understood data-loss window.

## Return to the current release

After completing the rollback exercise, rerun the current application deployment from GitHub or route traffic to the verified current revision. Recheck readiness and confirm the collector image digest matches the current release.

Finally run the manual Terraform `plan`. It must not report deployment-client metadata, remove the API revision name, or attempt to restore an older container image because those attributes belong to the application workflow.
