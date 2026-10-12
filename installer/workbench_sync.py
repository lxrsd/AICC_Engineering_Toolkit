#!/usr/bin/env python3
"""AICC Engineering Toolkit — automatic Workbench lifecycle synchronization.

Runs on the ENGINEER'S machine, invoked automatically by an AI-DLC runtime hook
as the governed lifecycle progresses (see hooks/aicc-workbench-sync.*). It:

  1. Resolves the current project's SAVED registration from .aicc/config.json
     (the stable local identity, selected harness, registered project_id, the
     Workbench API, and the UPDATE capability issued at registration).
  2. Locates the sanitized AI-DLC evidence manifest the governed lifecycle
     exported (never raw source, receipts, or engine state).
  3. Validates it against the AI-DLC evidence schema (same validator the backend
     uses) and scans for forbidden/sensitive content.
  4. Submits a lifecycle UPDATE to the SAME registered project via
     POST /api/engineer-projects/<project_id>/updates with the update_token.
     The server re-derives stage status from the evidence; this client sends no
     "completed/green" claims. It NEVER creates a new project per stage.

Honest + non-fatal by design: a missing registration, missing evidence, an
undeployed backend, or a bad response is reported and the lifecycle continues.
It never fabricates progress and never uploads anything the sanitizer rejects.

The engineer does nothing manually: no run id, no evidence upload, no AWS, no
AICC login. Stdlib only.

Usage (normally invoked by the hook, but runnable directly):
  workbench_sync.py [--target <project-dir>] [--evidence <manifest.json>]
                    [--api <url>] [--quiet]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.request
import urllib.error

HERE = pathlib.Path(__file__).resolve().parent
TOOLKIT_ROOT = HERE.parent
VALIDATORS = TOOLKIT_ROOT / "capabilities" / "ai-dlc" / "validators"
SCHEMA = VALIDATORS / "schema" / "evidence-manifest.schema.json"
AICC_CONFIG_REL = pathlib.Path(".aicc") / "config.json"
UPDATE_PATH = "/api/engineer-projects/{project_id}/updates"

SUPPORTED_TOOLS = {"kiro-cli", "claude-code"}
MAX_BYTES = 512 * 1024

# Candidate locations an AI-DLC export writes the sanitized manifest to, tried
# in order under the project dir. The hook may also pass --evidence explicitly.
EVIDENCE_CANDIDATES = [
    ".aicc/evidence/evidence-manifest.json",
    "engineering-hub/evidence/exports/latest/evidence-manifest.json",
]

# Must match the server's forbidden set so the client refuses locally what the
# backend would refuse. Keeps source/secrets/receipts/engine-state out.
FORBIDDEN = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bHUMAN_TURN\b"),
    re.compile(r"aws_secret_access_key\s*[=:]\s*\S+"),
    re.compile(r"sess_[0-9a-f-]{8,}"),
    re.compile(r"\.aidlc-engine\b"),
    re.compile(r"clone[-_ ]?id", re.I),
]

# Status values this client reports (never fabricated success).
SYNCED = "SYNCED"
NO_REGISTRATION = "NO_REGISTRATION"   # project not registered yet (run install)
NO_EVIDENCE = "NO_EVIDENCE"           # no exported manifest to sync yet
NOT_CONNECTED = "NOT_CONNECTED"       # backend unavailable / not deployed
FAILED = "FAILED"                     # reached but rejected / malformed


class SyncResult:
    def __init__(self, status: str, message: str, stages: list | None = None):
        self.status = status
        self.message = message
        self.stages = stages or []


def _load_config(target: pathlib.Path) -> dict:
    cfg_path = target / AICC_CONFIG_REL
    if not cfg_path.exists():
        return {}
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _load_schema() -> dict:
    try:
        return json.loads(SCHEMA.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _find_evidence(target: pathlib.Path, explicit: str | None) -> pathlib.Path | None:
    if explicit:
        p = pathlib.Path(explicit)
        return p if p.exists() else None
    for rel in EVIDENCE_CANDIDATES:
        p = target / rel
        if p.exists():
            return p
    return None


def _sanitize_and_validate(manifest: dict) -> dict:
    """Validate against the schema and refuse forbidden content. Returns a
    metadata-only projection (paths + hashes + stage/status + tests), never
    bodies."""
    tool = (manifest.get("tool") or {}).get("id")
    if tool not in SUPPORTED_TOOLS:
        raise ValueError(f"unsupported tool id {tool!r}")

    schema = _load_schema()
    if schema:
        sys.path.insert(0, str(VALIDATORS / "exporter"))
        import validate_evidence  # type: ignore
        errors = validate_evidence.validate(manifest, schema)
        if errors:
            raise ValueError(f"evidence failed schema validation: {errors[:3]}")

    blob = json.dumps(manifest)
    if len(blob.encode("utf-8")) > MAX_BYTES:
        raise ValueError("evidence manifest too large to sync")
    for pat in FORBIDDEN:
        if pat.search(blob):
            raise ValueError(f"refusing to sync: forbidden/sensitive content ({pat.pattern})")

    return {k: manifest[k] for k in (
        "schema_version", "generated_at", "tool", "framework", "intent",
        "stages", "tests", "artifacts", "approvals") if k in manifest}


def _post(url: str, body: dict) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("accept", "application/json")
    req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read(MAX_BYTES + 1).decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {"error": e.reason}
    except urllib.error.URLError:
        return 0, {}
    except json.JSONDecodeError:
        return -1, {}


def sync(target: pathlib.Path, evidence: str | None = None, api_override: str | None = None) -> SyncResult:
    cfg = _load_config(target)
    wb = cfg.get("workbench") if isinstance(cfg.get("workbench"), dict) else {}
    project_id = wb.get("project_id")
    update_token = wb.get("update_token")
    api = api_override or wb.get("api") or os.environ.get("AICC_WORKBENCH_API", "")

    if not project_id or not update_token:
        return SyncResult(NO_REGISTRATION,
                          "no registered project/update capability in .aicc/config.json; "
                          "run the Toolkit installer first (registration issues the update capability).")
    if not api:
        return SyncResult(NOT_CONNECTED, "no Workbench API configured for this project.")

    ev_path = _find_evidence(target, evidence)
    if ev_path is None:
        return SyncResult(NO_EVIDENCE,
                          "no exported AI-DLC evidence manifest found yet; nothing to sync "
                          "(the lifecycle exports evidence as stages produce artifacts).")
    try:
        manifest = json.loads(ev_path.read_text(encoding="utf-8"))
        sanitized = _sanitize_and_validate(manifest)
    except (OSError, json.JSONDecodeError) as exc:
        return SyncResult(FAILED, f"could not read evidence manifest {ev_path}: {exc}")
    except ValueError as exc:
        return SyncResult(FAILED, str(exc))

    url = f"{api.rstrip('/')}{UPDATE_PATH.format(project_id=project_id)}"
    status, payload = _post(url, {"update_token": update_token, "manifest": sanitized})

    if status in (404, 501):
        return SyncResult(NOT_CONNECTED,
                          f"Workbench update endpoint not available yet (HTTP {status}); "
                          "it ships in the private AICC_Unified backend.")
    if status == 0:
        return SyncResult(NOT_CONNECTED, f"could not reach the Workbench at {api}.")
    if status == 200 and isinstance(payload, dict) and payload.get("stages"):
        return SyncResult(SYNCED, f"synchronized project {project_id}", payload["stages"])
    err = payload.get("error") if isinstance(payload, dict) else ""
    return SyncResult(FAILED, f"Workbench update rejected (HTTP {status}){': ' + err if err else ''}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Automatic AICC Workbench lifecycle sync (no login, no manual upload).")
    ap.add_argument("--target", default=".", help="project directory (default: current dir)")
    ap.add_argument("--evidence", default=None, help="explicit path to the exported evidence-manifest.json")
    ap.add_argument("--api", default=None, help="override the Workbench API base URL")
    ap.add_argument("--quiet", action="store_true", help="only print on a real change/error")
    args = ap.parse_args(argv)

    result = sync(pathlib.Path(args.target).resolve(), args.evidence, args.api)

    # Non-fatal always: the hook must never break the engineer's lifecycle.
    if result.status == SYNCED:
        if not args.quiet:
            print(f"AICC Workbench: {result.message}")
            for s in result.stages:
                print(f"  {s.get('slug'):<13} {s.get('status')}  ({s.get('reason', '')})")
    elif not args.quiet:
        print(f"AICC Workbench sync ({result.status}): {result.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
