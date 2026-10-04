"""Archive Sonar-only cloud configuration and secrets outside the Git checkout.

Does not delete resources. Output is sensitive and created owner-readable only.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

PROJECT = "sonar-ai-prod"
REGION = "australia-southeast1"
GCLOUD = shutil.which("gcloud")


def run(*args):
    return subprocess.check_output([GCLOUD, *args, f"--project={PROJECT}"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if not GCLOUD:
        raise SystemExit("The existing gcloud CLI must be available on PATH")
    os.umask(0o077)
    args.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.directory.chmod(0o700)
    metadata = {
        "sql-instance": ("sql", "instances", "describe", "sonar-postgres"),
        "sql-databases": ("sql", "databases", "list", "--instance=sonar-postgres"),
        "sql-users": ("sql", "users", "list", "--instance=sonar-postgres"),
        "sql-backups": ("sql", "backups", "list", "--instance=sonar-postgres"),
        "api": ("run", "services", "describe", "sonar-api", f"--region={REGION}"),
        "collector": ("run", "jobs", "describe", "sonar-collector", f"--region={REGION}"),
        "migration": ("run", "jobs", "describe", "sonar-migration", f"--region={REGION}"),
        "scheduler": ("scheduler", "jobs", "describe", "sonar-collector-every-six-hours", f"--location={REGION}"),
        "iam": ("projects", "get-iam-policy", PROJECT),
    }
    for name, command in metadata.items():
        (args.directory / f"{name}.json").write_bytes(run(*command, "--format=json"))
        print(f"Archived {name}", flush=True)
    secrets = {}
    for secret in ("sonar-database-url", "sonar-gemini-api-key", "sonar-newsapi-key"):
        secrets[secret] = run("secrets", "versions", "access", "latest", f"--secret={secret}").decode()
    (args.directory / "secrets.json").write_text(json.dumps(secrets, indent=2))
    print("Archived runtime secrets (contents not printed)", flush=True)
    for prefix in ("application", "bootstrap"):
        run("storage", "cp", f"gs://{PROJECT}-terraform-state/{prefix}/default.tfstate", str(args.directory / f"{prefix}.tfstate"))
        print(f"Archived {prefix} Terraform state", flush=True)


if __name__ == "__main__":
    main()
