# Sonar application infrastructure

This root owns application infrastructure: required APIs, Artifact Registry, Cloud SQL, secret containers, runtime identities and IAM, the API service, collector/migration jobs, Scheduler, and an optional billing budget.

Bootstrap owns shared foundation APIs such as IAM, Service Usage, and Cloud Resource Manager. This root does not declare them again, so one GCP resource is never managed by two Terraform states. Billing APIs are enabled only when `manage_budget` is true.

Deployment is intentionally two-stage:

1. Apply with `deploy_workloads = false` to create the repository, database, secret containers, and identities.
2. Outside Terraform, create the `sonar` database user, add secret values, build and push the shared image, and obtain its digest.
3. Set `deploy_workloads = true` and `initial_image` to that digest, then review and apply again.

The first workload apply keeps Cloud Scheduler paused. After migrations and one manual collector execution succeed, set `scheduler_paused = false`, review the one-resource plan, and apply it to begin the six-hour schedule.

Terraform never owns secret versions. The database password and API keys must not appear in `.tfvars`, plans, state, Git, or chat. The image lifecycle ignores only the container image field because Phase 5 will deploy new image revisions; all other resource drift remains visible.
