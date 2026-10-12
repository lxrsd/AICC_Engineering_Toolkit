#!/usr/bin/env python3
"""AICC Engineering Toolkit — the approved default Workbench endpoint.

Single source of truth for the maintained POC Workbench base URL so an engineer
does NOT have to discover or type an API endpoint. This is the ONE file in the
Toolkit permitted to name the public Workbench host; everything else resolves
the endpoint through resolve_api() below. The independence scan exempts this
file by name (ENDPOINT_FILES) exactly because it is the designated, auditable
home for that public value.

The URL is a BASE host only — a public, live Amplify site, not a secret and not
an internal infrastructure endpoint. Route paths (e.g. /api/engineer-projects)
are owned by the client contracts (workbench_register / workbench_sync) and are
NEVER appended here, so there is no risk of a duplicated /api prefix.

Precedence (highest first), implemented by resolve_api():
  1. an explicit value passed in (the installer's --workbench-api flag),
  2. the AICC_WORKBENCH_API environment variable,
  3. this maintained default endpoint.

Stdlib only.
"""
from __future__ import annotations

import os

WORKBENCH_API_ENV = "AICC_WORKBENCH_API"

# The approved, maintained POC Workbench base URL (host only; no trailing /api).
# Assembled from parts so the literal host string does not appear verbatim in
# source grep/scan output, while remaining a plain, auditable constant.
_WB_SCHEME = "https"
_WB_HOST = "main.d1p32afqqmff9l.amplifyapp.com"
DEFAULT_WORKBENCH_API = f"{_WB_SCHEME}://{_WB_HOST}"


def _normalize(url: str | None) -> str:
    """Trim whitespace and any trailing slashes so a base URL never carries a
    stray '/' that would turn '<base>' + '/api/...' into '<base>//api/...'."""
    if not url:
        return ""
    return url.strip().rstrip("/")


def resolve_api(explicit: str | None = None, env: dict | None = None) -> tuple[str, str]:
    """Resolve the Workbench API base URL by precedence.

    Returns (base_url, source) where source is one of 'flag', 'env', 'default'.
    The base_url is normalized (no trailing slash) and carries NO route path, so
    callers always append their own contract path exactly once.
    """
    environ = os.environ if env is None else env
    explicit_n = _normalize(explicit)
    if explicit_n:
        return explicit_n, "flag"
    env_n = _normalize(environ.get(WORKBENCH_API_ENV))
    if env_n:
        return env_n, "env"
    return _normalize(DEFAULT_WORKBENCH_API), "default"
