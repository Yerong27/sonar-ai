# Terraform bootstrap

This root creates only the resources needed before normal remote-state Terraform can run:

- a versioned, private GCS state bucket;
- a GitHub Actions Workload Identity Pool and OIDC provider;
- a Terraform deployer service account and its infrastructure-management roles.

It intentionally does not create Sonar application resources. The first apply uses local state because the state bucket does not exist yet. After that apply, copy `backend.tf.example` to the ignored `backend.tf` and migrate this root's state into GCS.

Do not place credentials, passwords, API keys, or secret values in this directory. Review the IAM roles in `main.tf` before every apply.
