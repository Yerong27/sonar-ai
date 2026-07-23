variable "project_id" {
  description = "Existing GCP project that will host Sonar."
  type        = string
  default     = "sonar-ai-prod"
}

variable "region" {
  description = "Primary GCP region."
  type        = string
  default     = "australia-southeast1"
}

variable "state_bucket_name" {
  description = "Globally unique GCS bucket for Terraform state."
  type        = string
  default     = "sonar-ai-prod-terraform-state"
}

variable "github_repository" {
  description = "GitHub repository allowed to use Workload Identity Federation."
  type        = string
  default     = "Yerong27/sonar-ai"
}

variable "workload_identity_pool_id" {
  description = "Short ID for the GitHub Actions workload identity pool."
  type        = string
  default     = "github-actions"
}

variable "workload_identity_provider_id" {
  description = "Short ID for the GitHub Actions OIDC provider."
  type        = string
  default     = "github"
}

variable "grant_terraform_budget_role" {
  description = "Grant the Terraform deployer billing budget management when the caller has billing-account IAM permission."
  type        = bool
  default     = false
}

variable "billing_account_id" {
  description = "Billing account ID used only when grant_terraform_budget_role is true."
  type        = string
  default     = "019479-9F863D-88584D"
}
