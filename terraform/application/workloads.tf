resource "google_cloud_run_v2_service" "api" {
  count = var.deploy_workloads ? 1 : 0

  project             = var.project_id
  name                = "sonar-api"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account                  = google_service_account.api.email
    timeout                          = "60s"
    max_instance_request_concurrency = 20

    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = var.api_max_instances
    }

    containers {
      image = var.initial_image

      ports {
        name           = "http1"
        container_port = 8060
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "SONAR_CORS_ORIGINS"
        value = "${var.frontend_origin},http://localhost:5173,http://127.0.0.1:5173"
      }

      env {
        name = "DATABASE_URL"

        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      startup_probe {
        initial_delay_seconds = 2
        timeout_seconds       = 3
        period_seconds        = 5
        failure_threshold     = 12

        http_get {
          path = "/health/live"
          port = 8060
        }
      }

      liveness_probe {
        timeout_seconds   = 3
        period_seconds    = 30
        failure_threshold = 3

        http_get {
          path = "/health/live"
          port = 8060
        }
      }
    }

    volumes {
      name = "cloudsql"

      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.application,
    google_project_iam_member.runtime_cloud_sql_client,
    google_secret_manager_secret_iam_member.api_database_url,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "api_public" {
  count = var.deploy_workloads ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api[0].name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_job" "collector" {
  count = var.deploy_workloads ? 1 : 0

  project             = var.project_id
  name                = "sonar-collector"
  location            = var.region
  deletion_protection = false

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.collector.email
      timeout         = "900s"
      max_retries     = 2

      containers {
        image   = var.initial_image
        command = ["python"]
        args    = ["-m", "sonar.worker", "--once"]

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }

        env {
          name = "DATABASE_URL"

          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }

        env {
          name = "GEMINI_API_KEY"

          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.gemini_api_key.secret_id
              version = "latest"
            }
          }
        }

        env {
          name = "NEWSAPI_KEY"

          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.newsapi_key.secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      volumes {
        name = "cloudsql"

        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.application,
    google_project_iam_member.runtime_cloud_sql_client,
    google_secret_manager_secret_iam_member.collector_database_url,
    google_secret_manager_secret_iam_member.collector_gemini_api_key,
    google_secret_manager_secret_iam_member.collector_newsapi_key,
  ]
}

resource "google_cloud_run_v2_job" "migration" {
  count = var.deploy_workloads ? 1 : 0

  project             = var.project_id
  name                = "sonar-migration"
  location            = var.region
  deletion_protection = false

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.migration.email
      timeout         = "600s"
      max_retries     = 0

      containers {
        image   = var.initial_image
        command = ["alembic"]
        args    = ["upgrade", "head"]

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        env {
          name = "DATABASE_URL"

          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }

      volumes {
        name = "cloudsql"

        cloud_sql_instance {
          instances = [google_sql_database_instance.main.connection_name]
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }

  depends_on = [
    google_project_service.application,
    google_project_iam_member.runtime_cloud_sql_client,
    google_secret_manager_secret_iam_member.migration_database_url,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_collector_invoker" {
  count = var.deploy_workloads ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.collector[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_run_v2_job_iam_member" "deployer_migration_invoker" {
  count = var.deploy_workloads ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.migration[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.application_deployer.email}"
}

resource "google_cloud_scheduler_job" "collector" {
  count = var.deploy_workloads ? 1 : 0

  project          = var.project_id
  region           = var.region
  name             = "sonar-collector-every-six-hours"
  description      = "Run the Sonar collector as a single Cloud Run Job task"
  schedule         = var.collector_schedule
  time_zone        = var.collector_schedule_time_zone
  paused           = var.scheduler_paused
  attempt_deadline = "320s"

  retry_config {
    retry_count          = 2
    min_backoff_duration = "30s"
    max_backoff_duration = "300s"
    max_doublings        = 3
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.collector[0].name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_cloud_run_v2_job_iam_member.scheduler_collector_invoker,
    google_project_service.application,
  ]
}
