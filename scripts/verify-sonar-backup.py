"""Restore an SQL export to an explicitly named isolated local container.

Verify every exported table's row count and record the archive SHA-256.
No cloud resources are changed. The original archive is left untouched.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--container", required=True)
    args = parser.parse_args()
    if not args.container.startswith("sonar-backup-verify-"):
        raise SystemExit("Refusing to restore into a non-verification container")
    os.umask(0o077)
    args.archive.chmod(0o600)
    sql = gzip.decompress(args.archive.read_bytes())
    # Count pg_dump COPY rows independently of the database being restored.
    expected = {}
    current = None
    for line in sql.decode().splitlines():
        match = re.match(r"COPY public\.([a-z_]+) \(.*\) FROM stdin;", line)
        if match:
            current = match[1]
            expected[current] = 0
        elif line == r"\.":
            current = None
        elif current:
            expected[current] += 1
    if not expected or not expected.get("hn_story_snapshots"):
        raise SystemExit("Export contains no story data")
    command = ["docker", "exec", "-i", args.container, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "sonar", "-d", "sonar"]
    # Cloud SQL exports its platform ACLs, but not platform role definitions.
    # Recreate a non-login placeholder only in this isolated restore container.
    admin = command[:-1] + ["postgres"]
    subprocess.run(admin + ["-c", "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cloudsqlsuperuser') THEN CREATE ROLE cloudsqlsuperuser NOLOGIN; END IF; END $$;"], check=True, capture_output=True)
    subprocess.run(admin + ["-c", "DROP DATABASE IF EXISTS sonar WITH (FORCE)"], check=True, capture_output=True)
    subprocess.run(admin + ["-c", "CREATE DATABASE sonar OWNER sonar"], check=True, capture_output=True)
    restored = subprocess.run(command, input=sql, capture_output=True)
    if restored.returncode:
        print(restored.stderr.decode())
        raise SystemExit("Restore failed; cloud database must not be deleted")
    actual = {}
    for table, count in expected.items():
        query = f'SELECT count(*) FROM public."{table}"'
        actual[table] = int(subprocess.check_output(command + ["-tAc", query]))
        if actual[table] != count:
            raise SystemExit(f"Row count mismatch: {table}")
    schema_version = subprocess.check_output(command + ["-tAc", "SELECT version_num FROM alembic_version"]).decode().strip()
    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "archive": args.archive.name,
        "sha256": hashlib.sha256(args.archive.read_bytes()).hexdigest(),
        "restore_success": True,
        "schema_version": schema_version,
        "table_counts": actual,
        "method": "PostgreSQL 16 restore with ON_ERROR_STOP; compare all COPY row counts",
    }
    (args.archive.parent / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
