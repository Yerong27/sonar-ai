# Phase 4: GCP Terraform runbook

This runbook is for the Sonar GCP deployment in project `sonar-ai-prod`, region `australia-southeast1` (Sydney). It deliberately stops before Phase 5 CI/CD.

## What the two Terraform roots own

`terraform/bootstrap` solves the bootstrap cycle: Terraform cannot keep state in a GCS bucket or let GitHub impersonate a deployer until those resources exist. Its first apply therefore uses local state and creates only the state bucket, GitHub Workload Identity Federation, and the Terraform deployer identity.

`terraform/application` owns the actual platform:

```text
Sites frontend
    -> public Cloud Run API (sonar-api service account)
    -> Cloud SQL PostgreSQL

Cloud Scheduler (sonar-scheduler service account)
    -> Cloud Run collector Job (sonar-collector service account)
    -> Cloud SQL PostgreSQL

Cloud Run migration Job (sonar-migration service account)
    -> Cloud SQL PostgreSQL

Artifact Registry holds the shared API/collector/migration image.
Secret Manager injects runtime values; Terraform creates containers only.
```

Shared foundation APIs such as IAM, Service Usage, and Cloud Resource Manager remain owned only by the bootstrap state. The application state does not redeclare them. Billing APIs are included only when `manage_budget = true`.

The API has no permission to read Gemini or NewsAPI secrets. Scheduler has job-level permission to invoke only the collector. The API is capped at two instances to limit both cost and Cloud SQL connection pressure.

## Safety rules

- Never put a password, API key, token, or complete database URL in Terraform variables, `.tfvars`, plans, state, Git, or chat.
- Always inspect a saved plan before applying it.
- Do not disable Cloud SQL deletion protection just to make a plan convenient.
- A billing budget sends alerts; it is not a hard spending limit.
- Terraform ignores only each Cloud Run container's `image` field. It must continue to detect IAM, scaling, networking, secrets, CPU, memory, and other drift.

## 1. Bootstrap: commands you run personally

Confirm the intended account and project first:

```bash
gcloud auth list --filter=status:ACTIVE
gcloud config set project sonar-ai-prod
gcloud config set run/region australia-southeast1
gcloud config set artifacts/location australia-southeast1
```

Copy the non-secret example values, review every resource, then initialize and validate:

```bash
cd /Users/Djoker/Python/Sonar/terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform fmt -check
terraform validate
terraform plan -out=bootstrap.tfplan
terraform show bootstrap.tfplan
```

Expected plan categories: required bootstrap APIs, one private/versioned GCS bucket, one service account, its IAM grants, one WIF pool, one GitHub OIDC provider, and one WIF binding. It must not contain Cloud Run, Cloud SQL, Scheduler, application secrets, or secret values.

Only after reviewing that plan, apply the exact saved plan yourself:

```bash
terraform apply bootstrap.tfplan
terraform output
```

Then migrate bootstrap state from the local file into the newly created GCS bucket:

```bash
cp backend.tf.example backend.tf
terraform init -migrate-state
terraform state list
```

`backend.tf` is intentionally ignored because it is local backend configuration. Do not delete the local state file until `terraform state list` succeeds against GCS and the bucket contains the `bootstrap` state object.

If you want Terraform to manage the AUD 50 budget, first confirm that your account can edit billing-account IAM. Set `grant_terraform_budget_role = true` in the ignored bootstrap `terraform.tfvars`, review its plan, and apply it. Otherwise leave it false and configure the budget in the Billing console.

## 2. Application base infrastructure: commands you run personally

Initialize the application root directly against the remote-state bucket:

```bash
cd /Users/Djoker/Python/Sonar/terraform/application
cp terraform.tfvars.example terraform.tfvars
terraform init \
  -backend-config='bucket=sonar-ai-prod-terraform-state' \
  -backend-config='prefix=application'
terraform fmt -check
terraform validate
terraform plan -out=application-base.tfplan
terraform show application-base.tfplan
```

For the base plan, keep `deploy_workloads = false`. Expected categories are APIs, Artifact Registry, Cloud SQL and database, three empty Secret Manager containers, service accounts, and least-privilege IAM. It must not yet contain Cloud Run services/jobs or Scheduler because no application image exists.

Review and apply the exact saved plan yourself:

```bash
terraform apply application-base.tfplan
terraform output
```

In GCP Console/CLI, independently confirm:

- Cloud SQL is PostgreSQL 16, Enterprise, `db-f1-micro`, zonal, 10 GB SSD, backup enabled, and deletion protection enabled;
- Artifact Registry is in Sydney and has cleanup policies;
- all five runtime/deployer service accounts exist;
- all three Secret Manager containers exist but have no value versions;
- the API service account cannot access the Gemini or NewsAPI secrets.
- the Terraform deployer can act as only the four runtime/Scheduler identities defined in Terraform, not arbitrary service accounts through a project-wide grant.

## 3. Provision database credentials and secret values outside Terraform

Use a password manager to generate a strong random password. Do not paste it into this repository or conversation. Create the `sonar` Cloud SQL user through the GCP Console so the password is never present in shell history.

The database URL used by Cloud Run has this form:

```text
postgresql+psycopg://sonar:<URL-ENCODED-PASSWORD>@/sonar?host=/cloudsql/sonar-ai-prod:australia-southeast1:sonar-postgres
```

Add it as a new version of `sonar-database-url`. One safe terminal pattern is to read the complete URL without echoing it, then pipe it directly to Secret Manager:

```bash
read -s 'DATABASE_URL?Database URL: '
printf %s "$DATABASE_URL" | gcloud secrets versions add sonar-database-url --data-file=-
unset DATABASE_URL
```

Repeat that pattern for `sonar-gemini-api-key` and `sonar-newsapi-key`. Empty optional keys should still have an empty version if the Cloud Run Job references them. Confirm only version metadata, not payloads:

```bash
gcloud secrets versions list sonar-database-url
gcloud secrets versions list sonar-gemini-api-key
gcloud secrets versions list sonar-newsapi-key
```

## 4. Push the initial shared image

Authenticate Docker, build the existing shared image, and push it:

```bash
cd /Users/Djoker/Python/Sonar
gcloud auth configure-docker australia-southeast1-docker.pkg.dev

IMAGE='australia-southeast1-docker.pkg.dev/sonar-ai-prod/sonar/sonar-api'
docker build -f Dockerfile.api -t "$IMAGE:phase4-initial" .
docker push "$IMAGE:phase4-initial"
gcloud artifacts docker images describe "$IMAGE:phase4-initial" \
  --format='value(image_summary.digest)'
```

The final command should return `sha256:` followed by 64 hexadecimal characters. In `terraform/application/terraform.tfvars`, set `deploy_workloads = true` and set `initial_image` to the full repository path plus `@sha256:...`. A mutable tag is not accepted.

## 5. Create and verify workloads

Create a fresh plan after setting the digest:

```bash
cd /Users/Djoker/Python/Sonar/terraform/application
terraform plan -out=application-workloads.tfplan
terraform show application-workloads.tfplan
```

Expected additions: one public Cloud Run API service, collector and migration jobs, job-level IAM grants, and one Scheduler job. Confirm:

- API: min 0, max 2, concurrency 20, 1 CPU, 512 MiB, 60-second timeout;
- collector: one task, parallelism one, 1 CPU, 1 GiB, 15-minute timeout, at most two retries;
- migration: one task, parallelism one, 1 CPU, 512 MiB, 10-minute timeout, no retry;
- schedule: `0 */6 * * *` in UTC;
- Scheduler is initially paused so it cannot race the first migration;
- each image is pinned by digest;
- no secret payload appears in the plan.

Only then apply it yourself:

```bash
terraform apply application-workloads.tfplan
```

Run migrations before collector or API readiness validation:

```bash
gcloud run jobs execute sonar-migration \
  --region=australia-southeast1 \
  --wait

gcloud run jobs execute sonar-collector \
  --region=australia-southeast1 \
  --wait

API_URL="$(terraform output -raw api_url)"
curl -fsS "$API_URL/health/ready"
curl -fsS "$API_URL/api/status" | python -m json.tool
```

Finally inspect the API, migration, collector, Cloud SQL, and Scheduler logs in GCP. Do not treat a successful Terraform apply as proof that the application is healthy.

After all manual checks succeed, set `scheduler_paused = false` in the ignored application `terraform.tfvars`, create and inspect a new plan, and apply it. That plan should update only the Scheduler job from paused to active.

## Required personal learning change

Before Phase 4 is accepted, make one small Terraform change yourself—for example change the collector schedule from every six hours to every twelve hours—then run and explain the plan. Decide whether to apply or revert it. Do not enter Phase 5 until the bootstrap and application plans contain no unexplained changes and the runtime checks above pass.
