#!/usr/bin/env python3
"""Validate an AICC AI-DLC evidence manifest against the tool-independent contract.

Stdlib-only (no third-party dependencies) so it runs identically on any
developer machine and in GitHub CI without an install step. It implements the
subset of JSON-Schema semantics the evidence contract uses (type, required,
enum, const, pattern, additionalProperties, array items, minItems, minimum).

Honesty rule enforced here: this validator checks ONLY committed evidence. It
NEVER asserts that protected human-approval receipts were verified. The
optional `approvals` block is accepted as a DECLARED-not-verified statement and
its `verifiable_by_ci` flag must be false; validation never upgrades a
declaration into a verified approval.

Usage:
    validate_evidence.py <manifest.json> [--schema <schema.json>] [--repo-root <dir>]
                         [--check-artifacts]

Exit codes:
    0  manifest valid (and, with --check-artifacts, every artifact present with matching sha256)
    1  manifest invalid or an artifact is missing / hash-mismatched
    2  usage / IO error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from typing import Any


def _err(path: str, msg: str) -> str:
    loc = path or "<root>"
    return f"{loc}: {msg}"


def validate(node: Any, schema: dict, path: str = "") -> list[str]:
    """Return a list of human-readable validation errors (empty == valid)."""
    errors: list[str] = []

    expected_type = schema.get("type")
    if expected_type:
        if not _type_ok(node, expected_type):
            errors.append(_err(path, f"expected type {expected_type}, got {_json_type(node)}"))
            return errors  # further checks are meaningless on a type mismatch

    if "const" in schema and node != schema["const"]:
        errors.append(_err(path, f"must equal {schema['const']!r}, got {node!r}"))

    if "enum" in schema and node not in schema["enum"]:
        errors.append(_err(path, f"{node!r} is not one of {schema['enum']}"))

    if "pattern" in schema and isinstance(node, str):
        if not re.search(schema["pattern"], node):
            errors.append(_err(path, f"{node!r} does not match pattern {schema['pattern']}"))

    if isinstance(node, (int, float)) and not isinstance(node, bool):
        if "minimum" in schema and node < schema["minimum"]:
            errors.append(_err(path, f"{node} is below minimum {schema['minimum']}"))

    if expected_type == "object" or isinstance(node, dict):
        if isinstance(node, dict):
            for req in schema.get("required", []):
                if req not in node:
                    errors.append(_err(path, f"missing required property '{req}'"))
            props = schema.get("properties", {})
            if schema.get("additionalProperties") is False:
                for key in node:
                    if key not in props:
                        errors.append(_err(path, f"unexpected property '{key}'"))
            for key, subschema in props.items():
                if key in node:
                    errors.extend(validate(node[key], subschema, f"{path}.{key}" if path else key))

    if expected_type == "array" or isinstance(node, list):
        if isinstance(node, list):
            if "minItems" in schema and len(node) < schema["minItems"]:
                errors.append(_err(path, f"array has {len(node)} items, fewer than minItems {schema['minItems']}"))
            item_schema = schema.get("items")
            if item_schema:
                for i, item in enumerate(node):
                    errors.extend(validate(item, item_schema, f"{path}[{i}]"))

    return errors


def _json_type(node: Any) -> str:
    if isinstance(node, bool):
        return "boolean"
    if isinstance(node, str):
        return "string"
    if isinstance(node, int):
        return "integer"
    if isinstance(node, float):
        return "number"
    if isinstance(node, list):
        return "array"
    if isinstance(node, dict):
        return "object"
    if node is None:
        return "null"
    return type(node).__name__


def _type_ok(node: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(node, dict)
    if expected == "array":
        return isinstance(node, list)
    if expected == "string":
        return isinstance(node, str)
    if expected == "integer":
        return isinstance(node, int) and not isinstance(node, bool)
    if expected == "number":
        return isinstance(node, (int, float)) and not isinstance(node, bool)
    if expected == "boolean":
        return isinstance(node, bool)
    if expected == "null":
        return node is None
    return True


def sha256_of(file_path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def check_artifacts(manifest: dict, repo_root: pathlib.Path) -> list[str]:
    errors: list[str] = []
    for i, art in enumerate(manifest.get("artifacts", [])):
        rel = art.get("path", "")
        target = (repo_root / rel).resolve()
        try:
            target.relative_to(repo_root.resolve())
        except ValueError:
            errors.append(f"artifacts[{i}]: path '{rel}' escapes the repository root")
            continue
        if not target.is_file():
            errors.append(f"artifacts[{i}]: file not found: {rel}")
            continue
        actual = sha256_of(target)
        if actual != art.get("sha256"):
            errors.append(f"artifacts[{i}]: sha256 mismatch for {rel} (expected {art.get('sha256')}, got {actual})")
    return errors


def honesty_check(manifest: dict) -> list[str]:
    """Enforce the contract's non-fabrication rule on the optional approvals block."""
    errors: list[str] = []
    approvals = manifest.get("approvals")
    if approvals is not None:
        if approvals.get("verifiable_by_ci") is not False:
            errors.append(
                "approvals.verifiable_by_ci must be false: CI cannot verify protected "
                "approval receipts and must not claim otherwise"
            )
    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate an AICC AI-DLC evidence manifest.")
    parser.add_argument("manifest")
    default_schema = pathlib.Path(__file__).resolve().parent.parent / "schema" / "evidence-manifest.schema.json"
    parser.add_argument("--schema", default=str(default_schema))
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--check-artifacts", action="store_true",
                        help="also verify each artifact exists and its sha256 matches")
    args = parser.parse_args(argv)

    try:
        manifest = json.loads(pathlib.Path(args.manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read manifest {args.manifest}: {exc}", file=sys.stderr)
        return 2
    try:
        schema = json.loads(pathlib.Path(args.schema).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read schema {args.schema}: {exc}", file=sys.stderr)
        return 2

    errors = validate(manifest, schema)
    errors.extend(honesty_check(manifest))
    if args.check_artifacts and not errors:
        errors.extend(check_artifacts(manifest, pathlib.Path(args.repo_root)))

    if errors:
        print(f"INVALID: {args.manifest}", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"VALID: {args.manifest} (schema {manifest.get('schema_version')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
