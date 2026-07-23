output "state_bucket_name" {
  description = "Bucket to use for the application Terraform backend."
  value       = google_storage_bucket.terraform_state.name
}

output "terraform_deployer_email" {
  description = "Service account impersonated by the future Terraform workflow."
  value       = google_service_account.terraform_deployer.email
}

output "workload_identity_provider" {
  description = "Full WIF provider name consumed by GitHub authentication."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "workload_identity_pool_name" {
  description = "Full pool name passed to the application Terraform root."
  value       = google_iam_workload_identity_pool.github.name
}
