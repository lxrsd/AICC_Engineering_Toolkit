#!/usr/bin/env python3
"""AICC Engineering Toolkit — Workbench project registration client.

Runs on the ENGINEER'S machine. Registers the engineer's OWN project with the
AICC Workbench so they get a personal project/run identifier, a Workbench URL,
and six lifecycle stages initialized as pending. It does NOT submit evidence
(that is submit_evidence.py) and it does NOT touch our original certified
showcase runs.

------------------------------------------------------------------------------
REGISTRATION CONTRACT (client side; the backend lives in a SEPARATE private
repo and is NOT implemented here)
------------------------------------------------------------------------------
Request:
    POST  <api>/api/engineer-projects
    body  {
            "local_project_id": "<stable local uuid4 hex>",
            "tool":             "claude-code" | "kiro-cli",
            "harness":          "claude" | "kiro"
          }

Success response (201 Created on first registration, 200 OK on an idempotent
repeat registration with the same local_project_id):
    {
      "project_id":    "<server-generated project/run id>",
      "workbench_url": "<absolute https URL to THIS engineer's project>",
      "stages": [
        {"slug": "requirements", "status": "pending"},
        {"slug": "design",       "status": "pending"},
        {"slug": "approval",     "status": "pending"},
        {"slug": "code",         "status": "pending"},
        {"slug": "tests",        "status": "pending"},
        {"slug": "evidence",     "status": "pending"}
      ]
    }

Idempotency: a repeat POST with the same local_project_id MUST return the same
project_id and workbench_url (reuse on subsequent installations). The client
treats both 200 and 201 as success and simply records what the server returns.

------------------------------------------------------------------------------
MISSING BACKEND DEPENDENCY (honesty)
------------------------------------------------------------------------------
As of this Toolkit release the live Workbench API may NOT yet implement
`/api/engineer-projects`. A separate phase in the private AICC_Unified repo will
implement and deploy that endpoint. Until then this client will receive a 404 /
501 / connection error / unexpected shape, and it reports an honest
NOT_CONNECTED status. It NEVER fabricates a project_id or a working Workbench
URL, and it NEVER claims registration succeeded when it did not.

The API base URL is NOT hardcoded here (it is passed in by the caller / CLI /
env var); only the public documentation (README.md) names the live Workbench
host.

Stdlib only.
"""
from __future__ import annotations

import json
import ssl
import urllib.request
import urllib.error

import tls

REGISTER_PATH = "/api/engineer-projects"

# TLS policy for all requests from this client. Default: full verification with
# strict X.509 ON. The installer may flip relax_keyusage (opt-in only) via
# set_tls_policy(); it NEVER disables chain/hostname verification.
_RELAX_KEYUSAGE = False


def set_tls_policy(relax_keyusage: bool) -> None:
    global _RELAX_KEYUSAGE
    _RELAX_KEYUSAGE = bool(relax_keyusage)

# The six AI-DLC lifecycle stages, in order. The server initializes each as
# pending; the client verifies the server returned exactly these, all pending.
EXPECTED_STAGES = ("requirements", "design", "approval", "code", "tests", "evidence")

# Registration status values recorded in the project config.
STATUS_REGISTERED = "REGISTERED"       # valid registration succeeded
STATUS_NOT_CONNECTED = "NOT_CONNECTED"  # backend not available / not implemented yet
STATUS_FAILED = "FAILED"               # server reached but rejected / malformed

MAX_RESPONSE_BYTES = 256 * 1024


class RegisterError(Exception):
    """Honest, non-fatal registration failure. Carries a machine status so the
    installer can report NOT_CONNECTED vs FAILED without fabricating success."""

    def __init__(self, message: str, status: str = STATUS_FAILED):
        super().__init__(message)
        self.status = status


def _request(method: str, url: str, body: dict | None):
    """Perform one HTTP request. Returns (status_code, payload_dict).

    This is the TEST SEAM: tests monkeypatch workbench_register._request to
    simulate server responses with no network access.
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("accept", "application/json")
    if body is not None:
        req.add_header("content-type", "application/json")
    ctx = tls.build_ssl_context(relax_keyusage=_RELAX_KEYUSAGE)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            raw = r.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RegisterError("registration response too large", STATUS_FAILED)
            return r.status, json.loads(raw.decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            payload = {"error": e.reason}
        return e.code, payload
    except urllib.error.URLError as e:
        # Network-level failure, which includes TLS verification errors (the
        # SSLCertVerificationError is wrapped as URLError.reason). Classify it so
        # the engineer gets a precise cause + IT remediation, never a fabricated
        # success. Verification was NOT weakened to get here.
        code, detail = tls.diagnose_tls_error(e.reason if isinstance(e.reason, BaseException) else e)
        if code != tls.TLS_PROXY_NETWORK:
            raise RegisterError(f"TLS verification problem reaching the Workbench [{code}]: {detail}",
                                STATUS_NOT_CONNECTED)
        raise RegisterError(f"cannot reach Workbench at {url}: {e.reason}",
                            STATUS_NOT_CONNECTED)
    except ssl.SSLError as e:
        code, detail = tls.diagnose_tls_error(e)
        raise RegisterError(f"TLS problem reaching the Workbench [{code}]: {detail}",
                            STATUS_NOT_CONNECTED)
    except json.JSONDecodeError as e:
        raise RegisterError(f"Workbench returned a non-JSON response: {e}", STATUS_FAILED)


def _validate_success_payload(payload: dict) -> dict:
    """Validate a success payload against the contract. Raises RegisterError on
    any deviation so we never record a fabricated/partial registration."""
    if not isinstance(payload, dict):
        raise RegisterError("malformed registration response (not an object)", STATUS_FAILED)

    project_id = payload.get("project_id")
    workbench_url = payload.get("workbench_url")
    stages = payload.get("stages")

    if not isinstance(project_id, str) or not project_id.strip():
        raise RegisterError("registration response missing a valid 'project_id'", STATUS_FAILED)
    if not isinstance(workbench_url, str) or not workbench_url.startswith("https://"):
        raise RegisterError("registration response missing a valid https 'workbench_url'", STATUS_FAILED)
    if not isinstance(stages, list) or not stages:
        raise RegisterError("registration response missing 'stages'", STATUS_FAILED)

    slugs = []
    for s in stages:
        if not isinstance(s, dict):
            raise RegisterError("malformed stage entry in registration response", STATUS_FAILED)
        slug = s.get("slug")
        status = s.get("status")
        if slug is None:
            raise RegisterError("stage entry missing 'slug'", STATUS_FAILED)
        if status != "pending":
            raise RegisterError(
                f"stage {slug!r} is {status!r}, expected all six stages 'pending' at registration",
                STATUS_FAILED)
        slugs.append(slug)

    if tuple(slugs) != EXPECTED_STAGES:
        raise RegisterError(
            f"registration returned stages {slugs}, expected exactly {list(EXPECTED_STAGES)} (all pending)",
            STATUS_FAILED)

    result = {
        "project_id": project_id,
        "workbench_url": workbench_url,
        "stages": [{"slug": s["slug"], "status": "pending"} for s in stages],
    }
    # Phase 3 (optional, backward-compatible): the backend also returns an
    # update_token — the separate capability that authorizes pushing validated
    # lifecycle updates for THIS project. It is NOT part of the pinned view
    # contract and must never appear in the view URL; the installer stores it
    # privately so the sync hook can submit progress automatically. Older
    # backends omit it and registration still succeeds.
    update_token = payload.get("update_token")
    if isinstance(update_token, str) and update_token.strip():
        result["update_token"] = update_token
    return result


def register_project(api: str, local_project_id: str, tool: str, harness: str) -> dict:
    """Register (or idempotently re-register) the engineer's project.

    Returns a dict: {project_id, workbench_url, stages} on genuine success.

    Raises RegisterError (with .status NOT_CONNECTED or FAILED) when the backend
    is unavailable, has not implemented registration, or returns anything that
    does not satisfy the contract. The caller treats this as a non-fatal BLOCKED
    result — NEVER as success, and NEVER with a fabricated id/url.
    """
    if not api:
        raise RegisterError("no Workbench API base URL provided", STATUS_NOT_CONNECTED)
    url = f"{api.rstrip('/')}{REGISTER_PATH}"
    body = {"local_project_id": local_project_id, "tool": tool, "harness": harness}

    status, payload = _request("POST", url, body)

    # Backend reachable but endpoint not implemented / not found yet.
    if status in (404, 501):
        raise RegisterError(
            f"Workbench registration endpoint not available yet (HTTP {status}). "
            f"The backend ({REGISTER_PATH}) is implemented in a separate phase "
            f"(private AICC_Unified repo) and is not deployed yet.",
            STATUS_NOT_CONNECTED)

    if status in (200, 201):
        return _validate_success_payload(payload if isinstance(payload, dict) else {})

    # Any other response: honest failure, no fabrication.
    err = ""
    if isinstance(payload, dict):
        err = payload.get("error") or ""
    raise RegisterError(
        f"Workbench registration failed (HTTP {status}){': ' + err if err else ''}",
        STATUS_FAILED)
