provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  bootstrap_services = toset([
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "serviceusage.googleapis.com",
    "sts.googleapis.com",
    "storage.googleapis.com",
  ])

  terraform_project_roles = toset([
    "roles/artifactregistry.admin",
    "roles/cloudscheduler.admin",
    "roles/cloudsql.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/run.admin",
    "roles/secretmanager.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/serviceusage.serviceUsageConsumer",
  ])
}

resource "google_project_service" "bootstrap" {
  for_each = local.bootstrap_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "terraform_state" {
  name                        = var.state_bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.bootstrap]
}

resource "google_service_account" "terraform_deployer" {
  project      = var.project_id
  account_id   = "sonar-terraform-deployer"
  display_name = "Sonar Terraform deployer"

  depends_on = [google_project_service.bootstrap]
}

resource "google_project_iam_member" "terraform_deployer" {
  for_each = local.terraform_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.terraform_deployer.email}"
}

resource "google_storage_bucket_iam_member" "terraform_state" {
  bucket = google_storage_bucket.terraform_state.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.terraform_deployer.email}"
}

resource "google_billing_account_iam_member" "terraform_budget_manager" {
  count = var.grant_terraform_budget_role ? 1 : 0

  billing_account_id = var.billing_account_id
  role               = "roles/billing.costsManager"
  member             = "serviceAccount:${google_service_account.terraform_deployer.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = var.workload_identity_pool_id
  display_name              = "GitHub Actions"
  description               = "Keyless authentication for the Sonar GitHub repository"

  depends_on = [google_project_service.bootstrap]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = var.workload_identity_provider_id
  display_name                       = "Sonar GitHub repository"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == '${var.github_repository}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "terraform_github_wif" {
  service_account_id = google_service_account.terraform_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}
