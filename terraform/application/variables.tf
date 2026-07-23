variable "project_id" {
  description = "GCP project that hosts Sonar."
  type        = string
  default     = "sonar-ai-prod"
}

variable "region" {
  description = "Primary deployment region."
  type        = string
  default     = "australia-southeast1"
}

variable "github_repository" {
  description = "GitHub repository allowed to impersonate the application deployer."
  type        = string
  default     = "Yerong27/sonar-ai"
}

variable "workload_identity_pool_name" {
  description = "Full WIF pool name output by the bootstrap root."
  type        = string
  default     = "projects/476810083673/locations/global/workloadIdentityPools/github-actions"
}

variable "terraform_deployer_email" {
  description = "Terraform deployer email output by the bootstrap root."
  type        = string
  default     = "sonar-terraform-deployer@sonar-ai-prod.iam.gserviceaccount.com"
}

variable "frontend_origin" {
  description = "Production frontend origin allowed by FastAPI CORS."
  type        = string
  default     = "https://sonar-ai-radar.liyerongvv.chatgpt.site"
}

variable "collector_schedule" {
  description = "Cloud Scheduler cron expression. The default runs every six hours."
  type        = string
  default     = "0 */6 * * *"
}

variable "collector_schedule_time_zone" {
  description = "IANA time zone used to interpret collector_schedule."
  type        = string
  default     = "Etc/UTC"
}

variable "scheduler_paused" {
  description = "Keep scheduled collection paused until migrations and a manual collector run succeed."
  type        = bool
  default     = true
}

variable "api_min_instances" {
  description = "Minimum warm API instances. Zero avoids idle instance cost."
  type        = number
  default     = 0
}

variable "api_max_instances" {
  description = "Maximum API instances; limits cost and Cloud SQL connection pressure."
  type        = number
  default     = 2
}

variable "cloud_sql_tier" {
  description = "Cloud SQL machine tier for the Sonar environment."
  type        = string
  default     = "db-f1-micro"
}

variable "cloud_sql_deletion_protection" {
  description = "Protect the Cloud SQL instance from accidental Terraform deletion."
  type        = bool
  default     = true
}

variable "deploy_workloads" {
  description = "Create Cloud Run API/jobs and Scheduler only after an initial image exists."
  type        = bool
  default     = false
}

variable "initial_image" {
  description = "Initial Artifact Registry image pinned by sha256 digest; required when deploy_workloads is true."
  type        = string
  default     = ""

  validation {
    condition     = var.initial_image == "" || can(regex("@sha256:[0-9a-f]{64}$", var.initial_image))
    error_message = "initial_image must be empty or an image reference ending in @sha256:<64 lowercase hex characters>."
  }
}

variable "manage_budget" {
  description = "Create a billing budget when the applying identity has billing-account permission."
  type        = bool
  default     = false
}

variable "billing_account_id" {
  description = "Billing account ID used only when manage_budget is true."
  type        = string
  default     = "019479-9F863D-88584D"
}

variable "monthly_budget_amount" {
  description = "Monthly budget amount in the billing account's currency. This is an alert, not a hard spending cap."
  type        = number
  default     = 50
}
