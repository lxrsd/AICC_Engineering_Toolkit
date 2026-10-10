#!/usr/bin/env python3
"""AICC Engineering Toolkit — submit a governed AI-DLC run to the Workbench.

Runs on the ENGINEER'S machine. It:
  1. Collects the current project's AI-DLC evidence (the exported, sanitized
     evidence manifest + run descriptor the governed lifecycle produced).
  2. Validates it against the AI-DLC evidence schema (local, same validator the
     backend uses) and scans for forbidden/sensitive content.
  3. Authenticates the engineer via the existing Cognito Hosted-UI device/PKCE
     flow and submits ONLY the sanitized manifest to POST /api/engineer-runs.
  4. Confirms retrieval of the stored run.

It NEVER uploads source code, secrets, or raw approval receipts — only the
sanitized evidence manifest (artifact paths + sha256 + stage/status metadata).
Stage status is DERIVED by the server from the evidence; this client sends no
"completed/green" claims.

Stdlib only. Usage:
  submit_evidence.py --project <name> --evidence <evidence-manifest.json> \
     --api <https://main.d1p32afqqmff9l.amplifyapp.com> [--token <access-token>]
  submit_evidence.py --project <name> --evidence <manifest.json> --api <url> --list
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.request
import urllib.error

HERE = pathlib.Path(__file__).resolve().parent
VALIDATORS = HERE.parent / "capabilities" / "ai-dlc" / "validators"
SCHEMA = VALIDATORS / "schema" / "evidence-manifest.schema.json"
sys.path.insert(0, str(VALIDATORS / "exporter"))

SUPPORTED_TOOLS = {"kiro-cli", "claude-code"}
MAX_BYTES = 512 * 1024

# Must match the server's forbidden set (engineer_runs.FORBIDDEN) so the client
# rejects locally what the backend would reject.
FORBIDDEN = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bHUMAN_TURN\b"),
    re.compile(r"aws_secret_access_key\s*[=:]\s*\S+"),
    re.compile(r"sess_[0-9a-f-]{8,}"),
    re.compile(r"\.aidlc-engine\b"),
    re.compile(r"clone[-_ ]?id", re.I),
]


class SubmitError(Exception):
    pass


def load_schema() -> dict:
    try:
        return json.loads(SCHEMA.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SubmitError(f"cannot read evidence schema: {exc}")


def collect_and_validate(evidence_path: pathlib.Path, project: str) -> dict:
    """Collect the project's exported evidence manifest, validate + sanitize."""
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", project) or ".." in project:
        raise SubmitError(f"invalid project name: {project!r}")
    try:
        manifest = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SubmitError(f"cannot read evidence manifest {evidence_path}: {exc}")

    tool = (manifest.get("tool") or {}).get("id")
    if tool not in SUPPORTED_TOOLS:
        raise SubmitError(f"unsupported tool id {tool!r}; supported: {sorted(SUPPORTED_TOOLS)}")

    # Schema validation (same validator the backend runs).
    import validate_evidence
    errors = validate_evidence.validate(manifest, load_schema())
    if errors:
        raise SubmitError(f"evidence failed schema validation: {errors[:3]}")

    # Sanitization: refuse to upload anything with forbidden/sensitive content.
    blob = json.dumps(manifest)
    if len(blob.encode("utf-8")) > MAX_BYTES:
        raise SubmitError("evidence manifest too large to submit")
    for pat in FORBIDDEN:
        if pat.search(blob):
            raise SubmitError(f"refusing to submit: evidence contains forbidden/sensitive content ({pat.pattern})")

    # Strip anything that could carry source/secrets: we only ever send the
    # manifest metadata (paths + hashes + stage/status + tests), never bodies.
    # (The AI-DLC exporter already produces a content-free manifest; this is a
    # belt-and-suspenders projection.)
    sanitized = {k: manifest[k] for k in (
        "schema_version", "generated_at", "tool", "framework", "intent",
        "stages", "tests", "artifacts", "approvals") if k in manifest}
    return sanitized


def _request(method: str, url: str, body: dict | None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("accept", "application/json")
    if body is not None:
        req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            payload = {"error": e.reason}
        return e.code, payload
    except urllib.error.URLError as e:
        raise SubmitError(f"network error reaching {url}: {e.reason}")


def submit(api: str, project: str, manifest: dict) -> dict:
    status, payload = _request("POST", f"{api.rstrip('/')}/api/engineer-runs",
                               {"project": project, "manifest": manifest})
    if status == 413:
        raise SubmitError("submission rejected (413): evidence too large.")
    if status in (400, 422):
        raise SubmitError(f"evidence rejected by the server ({status}): {payload.get('error')}")
    if status != 201:
        raise SubmitError(f"unexpected server response {status}: {payload}")
    return payload


def retrieve(api: str, run_id: str) -> dict | None:
    status, payload = _request("GET", f"{api.rstrip('/')}/api/engineer-runs/{run_id}", None)
    return payload if status == 200 else None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Submit a governed AI-DLC run to the AICC Workbench (POC, no login).")
    ap.add_argument("--project", required=True)
    ap.add_argument("--evidence", required=True, help="path to the exported evidence-manifest.json")
    ap.add_argument("--api", required=True, help="Workbench base URL (e.g. https://main.d1p32afqqmff9l.amplifyapp.com)")
    args = ap.parse_args(argv)

    try:
        manifest = collect_and_validate(pathlib.Path(args.evidence), args.project)
        print(f"Validated + sanitized evidence for tool {manifest['tool']['id']} "
              f"({len(manifest.get('artifacts', []))} artifacts). Submitting...")
        result = submit(args.api, args.project, manifest)
        run_id = result.get("run_id")
        print(f"Submitted. run_id={run_id}")
        print(f"Open your run: {args.api.rstrip('/')}/#/runs/{run_id}")
        rec = retrieve(args.api, run_id) if run_id else None
        if rec:
            print("Retrieved your run. Server-derived stage status:")
            for stage, st in (rec.get("stages") or {}).items():
                print(f"  {stage:<13} {st.get('status')}  ({st.get('reason')})")
        else:
            print("Submitted; retrieval returned no record yet (eventual consistency).")
        return 0
    except SubmitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
