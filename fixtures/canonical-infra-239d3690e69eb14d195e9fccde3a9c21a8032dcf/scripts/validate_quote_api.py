#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "k8s/base/api.deployment.yaml"
SERVICE = ROOT / "k8s/base/api.service.yaml"
EXTERNAL_SECRET = ROOT / "k8s/base/externalsecret.yaml"


def require(text: str, value: str, source: Path, errors: list[str]) -> None:
    if value not in text:
        errors.append(f"{source.relative_to(ROOT)} is missing required contract: {value}")


def main() -> int:
    errors: list[str] = []
    deployment = DEPLOYMENT.read_text()
    service = SERVICE.read_text()
    external_secret = EXTERNAL_SECRET.read_text()

    for value in (
        "containerPort: 8081",
        '{name: BIND_ADDRESS, value: "0.0.0.0:8081"}',
        "httpGet: {path: /readyz, port: http}",
        "httpGet: {path: /healthz, port: http}",
        "{name: GEMINI_MODEL, value: gemini-3.6-pro}",
        "envFrom: [{secretRef: {name: canonical-api-runtime}}]",
    ):
        require(deployment, value, DEPLOYMENT, errors)

    if deployment.count("httpGet: {path: /readyz, port: http}") != 1:
        errors.append("canonical API must expose exactly one /readyz probe")
    if deployment.count("httpGet: {path: /healthz, port: http}") != 1:
        errors.append("canonical API must expose exactly one /healthz probe")
    if "gemini-3.1-pro-preview" in deployment:
        errors.append("obsolete Gemini model remains in the API deployment")

    for value in (
        "port: 8081",
        "targetPort: http",
    ):
        require(service, value, SERVICE, errors)

    required_secret_keys = {
        "DATABASE_URL": "dd/canonical/api/database-url",
        "CANONICAL_INTERNAL_AUTH_TOKEN": "dd/canonical/api/internal-auth-token",
        "SHARED_AUTH_INTROSPECT_SECRET": "dd/shared-auth/canonical/introspect-secret",
        "GEMINI_API_KEY": "dd/canonical/api/gemini-api-key",
    }
    for key, remote in required_secret_keys.items():
        require(external_secret, f"secretKey: {key}", EXTERNAL_SECRET, errors)
        require(external_secret, f"remoteRef: {{key: {remote}}}", EXTERNAL_SECRET, errors)
        if external_secret.count(f"secretKey: {key}") != 1:
            errors.append(f"ExternalSecret must declare {key} exactly once")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("canonical quote API port, probe, model, and secret contracts passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
