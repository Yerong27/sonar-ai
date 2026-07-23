# Phase 5: GitHub Actions and public cutover

Phase 5 separates application delivery from infrastructure ownership. It uses GitHub's OIDC token and the existing GCP Workload Identity Federation provider; it does not use a service-account JSON key or a GitHub secret.

## Workflow ownership

| Workflow | Trigger | GCP identity | Responsibility |
| --- | --- | --- | --- |
| `CI` | pull request and push to `main` | none | lint, migrations, PostgreSQL tests, frontend build, image build, Terraform validation |
| `Deploy application` | successful `CI` run for a push to `main` | `sonar-application-deployer` | build/push one image, migrate, update collector, deploy and verify API |
| `Terraform application infrastructure` | manual only | `sonar-terraform-deployer` | plan or apply application infrastructure using GCS remote state |

Terraform owns Cloud Run runtime configuration, identities, IAM, Cloud SQL, secrets, scaling, Scheduler, and other infrastructure. The application workflow owns the shared container image, API revision name, and deployment-client metadata. Terraform ignores only those exact attributes and continues to report other drift.

## One-time GitHub setup you must perform

In `Yerong27/sonar-ai`, open **Settings → Environments**:

1. Create `production` for application deployments.
2. Create `infrastructure` for the manual Terraform workflow.
3. On `infrastructure`, add required reviewers if the repository plan supports deployment protection rules.
4. Restrict both environments to the `main` branch.

No GitHub Actions secret is required. The project ID, region, WIF provider, deployer emails, resource names, and the initial Terraform image digest are non-secret repository configuration and are written directly in the workflow files.

The WIF provider accepts tokens only when `assertion.repository == 'Yerong27/sonar-ai'`. The service-account bindings then determine whether the token can impersonate the application deployer or Terraform deployer. GitHub jobs also request only `contents: read` and `id-token: write`.

## CI sequence

The CI workflow starts PostgreSQL 16 as an isolated service container, applies Alembic to a clean `sonar_test` database, verifies that `current` equals `heads`, and runs the full test suite. Separate jobs build the frontend, build the production container, and validate both Terraform roots.

The application workflow cannot start from a pull request or a failed CI run. Its condition requires a successful `push` CI run whose branch is `main` and whose source repository is this repository.

## Application deployment order

The deployment uses one image identified by both the tested commit SHA and its immutable Artifact Registry digest:

1. authenticate to GCP through WIF;
2. build and push the exact commit tested by CI;
3. record the previous API revision/image and collector image;
4. update and execute the migration job;
5. only after migration succeeds, update the collector image;
6. deploy a new API revision from the same digest;
7. retry `/health/ready` until it succeeds or the workflow fails;
8. write the new and previous deployment identifiers to the workflow summary.

Migrations must remain backward-compatible. If the workflow fails after a migration succeeds, the previous API may continue running against the new schema. The workflow never runs `alembic downgrade` automatically.

## First workflow verification you must perform

After reviewing the YAML and committing it as the dedicated Phase 5 commit:

1. Push a branch and open a pull request. Confirm all four CI jobs pass.
2. Deliberately make one harmless workflow change and diagnose one real failed run from its logs before correcting it.
3. Merge or push the verified commit to `main` and confirm `Deploy application` starts only after `CI` succeeds.
4. Compare the workflow commit SHA, Artifact Registry digest, Cloud Run API revision, migration execution, and collector image.
5. Verify `/health/ready` and `/api/status` from the URL recorded in the summary.
6. Follow the rollback runbook once, verify the previous revision, and then redeploy the current commit.
7. Manually run the Terraform workflow with `operation=plan`; it must not propose restoring an older image.

Phase 5 is not accepted until these real GitHub and GCP checks, the rollback exercise, and the Sites cutover below have all succeeded.

## Sites cutover

The Sites project ID remains in `frontend/.openai/hosting.json`. Add this non-secret production runtime value to the existing Sites project:

```text
NEXT_PUBLIC_SONAR_API_BASE=https://sonar-api-4akcp3ehqa-ts.a.run.app
```

Then build, save, and publish a new Sites version. Verify in the browser that:

- the banner no longer says the dashboard is using its demonstration snapshot;
- `/api/status` data and timestamps match Cloud SQL;
- story links open the corresponding Hacker News item;
- topic/bubble interactions filter the related stories;
- browser developer tools show no CORS failure;
- `POST /api/run-once` returns `404` or `405` and is not present in OpenAPI.

Publishing is intentionally a user-owned approval step under the migration plan.
