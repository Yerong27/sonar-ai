resource "google_billing_budget" "sonar" {
  count = var.manage_budget ? 1 : 0

  billing_account = var.billing_account_id
  display_name    = "Sonar monthly budget"

  budget_filter {
    projects               = ["projects/${data.google_project.current.number}"]
    credit_types_treatment = "INCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      currency_code = "AUD"
      units         = tostring(var.monthly_budget_amount)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.8
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  depends_on = [google_project_service.application]
}
