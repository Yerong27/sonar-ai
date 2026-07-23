provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "current" {
  project_id = var.project_id
}

locals {
  application_services = toset(concat([
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "sqladmin.googleapis.com",
    ], var.manage_budget ? [
    "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com",
  ] : []))

  runtime_service_accounts = {
    api       = google_service_account.api.email
    collector = google_service_account.collector.email
    migration = google_service_account.migration.email
  }

  terraform_act_as_service_accounts = merge(local.runtime_service_accounts, {
    scheduler = google_service_account.scheduler.email
  })

  application_deployer_project_roles = toset([
    "roles/artifactregistry.writer",
    "roles/logging.viewer",
    "roles/run.developer",
    "roles/serviceusage.serviceUsageConsumer",
  ])
}

check "initial_image_is_ready" {
  assert {
    condition     = !var.deploy_workloads || can(regex("@sha256:[0-9a-f]{64}$", var.initial_image))
    error_message = "Set initial_image to an Artifact Registry sha256 digest before enabling deploy_workloads."
  }
}

resource "google_project_service" "application" {
  for_each = local.application_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "application" {
  project       = var.project_id
  location      = var.region
  repository_id = "sonar"
  description   = "Sonar application images"
  format        = "DOCKER"

  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-recent-versions"
    action = "KEEP"

    most_recent_versions {
      keep_count = 5
    }
  }

  cleanup_policies {
    id     = "delete-old-untagged"
    action = "DELETE"

    condition {
      tag_state  = "UNTAGGED"
      older_than = "1209600s"
    }
  }

  depends_on = [google_project_service.application]
}

resource "google_sql_database_instance" "main" {
  project             = var.project_id
  name                = "sonar-postgres"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = var.cloud_sql_deletion_protection

  settings {
    tier              = var.cloud_sql_tier
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 10
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      start_time                     = "02:00"
      point_in_time_recovery_enabled = false
    }

    ip_configuration {
      ipv4_enabled = true
    }

    maintenance_window {
      day          = 7
      hour         = 3
      update_track = "stable"
    }
  }

  depends_on = [google_project_service.application]
}

resource "google_sql_database" "sonar" {
  project  = var.project_id
  name     = "sonar"
  instance = google_sql_database_instance.main.name
}

resource "google_secret_manager_secret" "database_url" {
  project   = var.project_id
  secret_id = "sonar-database-url"

  replication {
    auto {}
  }

  depends_on = [google_project_service.application]
}

resource "google_secret_manager_secret" "gemini_api_key" {
  project   = var.project_id
  secret_id = "sonar-gemini-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.application]
}

resource "google_secret_manager_secret" "newsapi_key" {
  project   = var.project_id
  secret_id = "sonar-newsapi-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.application]
}

resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "sonar-api"
  display_name = "Sonar API runtime"

  depends_on = [google_project_service.application]
}

resource "google_service_account" "collector" {
  project      = var.project_id
  account_id   = "sonar-collector"
  display_name = "Sonar collector runtime"

  depends_on = [google_project_service.application]
}

resource "google_service_account" "migration" {
  project      = var.project_id
  account_id   = "sonar-migration"
  display_name = "Sonar database migration runtime"

  depends_on = [google_project_service.application]
}

resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = "sonar-scheduler"
  display_name = "Sonar collector scheduler"

  depends_on = [google_project_service.application]
}

resource "google_service_account" "application_deployer" {
  project      = var.project_id
  account_id   = "sonar-application-deployer"
  display_name = "Sonar GitHub application deployer"

  depends_on = [google_project_service.application]
}

resource "google_project_iam_member" "runtime_cloud_sql_client" {
  for_each = local.runtime_service_accounts

  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${each.value}"
}

resource "google_secret_manager_secret_iam_member" "api_database_url" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "collector_database_url" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.collector.email}"
}

resource "google_secret_manager_secret_iam_member" "collector_gemini_api_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.collector.email}"
}

resource "google_secret_manager_secret_iam_member" "collector_newsapi_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.newsapi_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.collector.email}"
}

resource "google_secret_manager_secret_iam_member" "migration_database_url" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.migration.email}"
}

resource "google_project_iam_member" "application_deployer" {
  for_each = local.application_deployer_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.application_deployer.email}"
}

resource "google_service_account_iam_member" "application_deployer_runtime_user" {
  for_each = local.runtime_service_accounts

  service_account_id = "projects/${var.project_id}/serviceAccounts/${each.value}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.application_deployer.email}"
}

resource "google_service_account_iam_member" "terraform_deployer_runtime_user" {
  for_each = local.terraform_act_as_service_accounts

  service_account_id = "projects/${var.project_id}/serviceAccounts/${each.value}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${var.terraform_deployer_email}"
}

resource "google_service_account_iam_member" "application_github_wif" {
  service_account_id = google_service_account.application_deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${var.workload_identity_pool_name}/attribute.repository/${var.github_repository}"
}
