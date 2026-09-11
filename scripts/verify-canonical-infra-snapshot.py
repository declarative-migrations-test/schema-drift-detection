#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "239d3690e69eb14d195e9fccde3a9c21a8032dcf"
SNAPSHOT = ROOT / f"fixtures/canonical-infra-{SOURCE_COMMIT}"
MANIFEST = SNAPSHOT / "manifest.json"
EXPECTED_REPOSITORY = "canonical-cloud/canonical-infra"
EXPECTED_FILES = {
    "k8s/base/api.deployment.yaml": "fe7f461273a981368e686288d2a1fe966b816f28",
    "k8s/base/api.service.yaml": "56d93cc6fde4b5cd045634f034e2b097b1694986",
    "k8s/base/externalsecret.yaml": "a057cca5db69c7aa7d8ca04a86614a8b2df11097",
    "scripts/validate_quote_api.py": "34c6ea926066ce00a85a711318e30f3d32e9f73f",
}


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("source_repository") != EXPECTED_REPOSITORY:
        raise SystemExit("snapshot source repository drifted")
    if manifest.get("source_commit") != SOURCE_COMMIT:
        raise SystemExit("snapshot source commit drifted")
    if manifest.get("files") != EXPECTED_FILES:
        raise SystemExit("snapshot manifest file pins drifted")

    actual_files = {
        path.relative_to(SNAPSHOT).as_posix()
        for path in SNAPSHOT.rglob("*")
        if path.is_file()
    }
    expected_snapshot_files = set(EXPECTED_FILES) | {"manifest.json"}
    if actual_files != expected_snapshot_files:
        missing = sorted(expected_snapshot_files - actual_files)
        extra = sorted(actual_files - expected_snapshot_files)
        raise SystemExit(f"snapshot file set drifted; missing={missing}, extra={extra}")

    for relative, expected_sha in EXPECTED_FILES.items():
        path = SNAPSHOT / relative
        if path.is_symlink():
            raise SystemExit(f"snapshot member must not be a symlink: {relative}")
        actual_sha = git_blob_sha(path.read_bytes())
        if actual_sha != expected_sha:
            raise SystemExit(
                f"snapshot blob mismatch for {relative}: expected {expected_sha}, got {actual_sha}"
            )

    print(
        "verified exact Canonical quote GitOps snapshot "
        f"{EXPECTED_REPOSITORY}@{SOURCE_COMMIT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
