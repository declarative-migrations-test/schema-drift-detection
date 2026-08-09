#!/usr/bin/env python3
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "bootstrap-manifest.json").read_text())
source = json.loads((root / "canonical-quote-source.json").read_text())
required = [
    "README.md",
    "AGENTS.md",
    "LICENSE",
    ".gitmodules",
    "bootstrap-manifest.json",
    "production-dependency.json",
    "canonical-quote-source.json",
    "scripts/build-dpm.sh",
    "scripts/test-schema-drift.sh",
]
missing = [path for path in required if not (root / path).exists()]
if missing:
    raise SystemExit(f"missing required files: {missing}")
expected_dpm = "d05a7880987ddaa271fa88b52c787390ef12b899"
expected_source = "7987c05944df5c03ff2fcbeeedf2c8e79f973d75"
expected_schema = "712f1269da3c8dfd381af9c69a81e549a4eb52be3e4f49558ec1a5edf205e191"
if manifest["production_dependency"]["commit"] != expected_dpm:
    raise SystemExit("production dependency pin drifted")
dependency = json.loads((root / "production-dependency.json").read_text())
if dependency["commit"] != expected_dpm:
    raise SystemExit("production dependency ledger drifted")
if source["dpmCommit"] != expected_dpm:
    raise SystemExit("Canonical quote dpm pin drifted")
if source["sourceCommit"] != expected_source:
    raise SystemExit("Canonical quote source pin drifted")
if source["schemaSha256"] != expected_schema:
    raise SystemExit("Canonical quote schema digest drifted")
workflow = (root / ".github/workflows/ci.yml").read_text()
for required_text in (
    expected_source,
    "canonical-cloud/canonical-api-server.rs",
    "scripts/test-declarative-postgres.sh",
    "persist-credentials: false",
    "postgres:17",
):
    if required_text not in workflow:
        raise SystemExit(f"workflow omits {required_text}")
for path in root.rglob("*"):
    relative = path.relative_to(root)
    if not path.is_file() or ".git" in relative.parts or "vendor" in relative.parts:
        continue
    if path.stat().st_size > 1_000_000:
        continue
    try:
        text = path.read_text()
    except UnicodeDecodeError:
        continue
    if any(marker in text for marker in ("<" * 7, "=" * 7, ">" * 7)):
        raise SystemExit(f"conflict marker in {path}")
    if re.search(r"gh[pousr]_[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY", text):
        raise SystemExit(f"credential-shaped content in {path}")
print(
    f"validated {manifest['organization']}/{manifest['repository']} at "
    f"Canonical source {expected_source}"
)
