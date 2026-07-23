output "artifact_registry_repository" {
  description = "Docker repository path used for the shared application image."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.application.repository_id}"
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL Unix socket connection name used by Cloud Run."
  value       = google_sql_database_instance.main.connection_name
}

output "secret_names" {
  description = "Secret containers whose values must be added outside Terraform."
  value = {
    database_url   = google_secret_manager_secret.database_url.secret_id
    gemini_api_key = google_secret_manager_secret.gemini_api_key.secret_id
    newsapi_key    = google_secret_manager_secret.newsapi_key.secret_id
  }
}

output "application_deployer_email" {
  description = "Service account used by the Phase 5 application workflow."
  value       = google_service_account.application_deployer.email
}

output "api_url" {
  description = "Public API URL after deploy_workloads is enabled."
  value       = try(google_cloud_run_v2_service.api[0].uri, null)
}

output "collector_job_name" {
  description = "Collector job name after deploy_workloads is enabled."
  value       = try(google_cloud_run_v2_job.collector[0].name, null)
}

output "migration_job_name" {
  description = "Migration job name after deploy_workloads is enabled."
  value       = try(google_cloud_run_v2_job.migration[0].name, null)
}
