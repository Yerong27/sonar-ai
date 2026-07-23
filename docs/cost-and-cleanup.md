# GCP cost and cleanup

Sonar is intentionally sized for low traffic: the API can scale to zero and is capped at two instances, the collector runs once every six hours, and Cloud SQL uses a small zonal instance without HA. The manually configured billing budget is an alert, not a spending cap.

## Routine cost checks

- Review Billing reports by service and SKU.
- Confirm the Scheduler frequency is still appropriate.
- Check Cloud Run job duration, retry counts, and Gemini/NewsAPI usage.
- Confirm Artifact Registry cleanup policies retain only recent images and delete old untagged images.
- Review Cloud SQL storage growth and backup usage.

## Pause variable workloads

To stop scheduled collection without deleting data, pause the Scheduler job:

```bash
gcloud scheduler jobs pause sonar-collector-every-six-hours \
  --location=australia-southeast1
```

Resume it only after confirming the desired schedule:

```bash
gcloud scheduler jobs resume sonar-collector-every-six-hours \
  --location=australia-southeast1
```

The Cloud Run API already has zero minimum instances. Cloud SQL continues to incur cost while it exists, even when the API and jobs are idle.

## Destructive cleanup boundary

Do not run `terraform destroy` as a routine pause mechanism. Cloud SQL deletion protection intentionally blocks accidental destruction, and destroying the database can permanently remove operational history.

Before any permanent cleanup:

1. pause Scheduler;
2. export or back up data that must be retained;
3. record active secret versions and container digests;
4. inspect a saved Terraform destroy plan;
5. explicitly decide whether Cloud SQL, its backups, Terraform state, and the Sites frontend should be retained;
6. disable deletion protection only as a separate, deliberate change.

The GCS Terraform-state bucket and bootstrap identity are foundation resources. Do not delete them before all application resources and retained state have been accounted for.
