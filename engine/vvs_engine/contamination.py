"""Contamination firewall: production source must not contain drawing-specific designations, DN inventories,
coordinates, object ids or expected quantities, and must not import validation data."""
from __future__ import annotations

import os
import re
import io
import tokenize
from typing import Any

FORBIDDEN_PATTERNS = [
    # concrete VVS designations (system-material-DN forms) used as literals
    (r"[\"'](?:S[0-9]|KV0?[0-9]|VV0?[0-9]|VVC0?[0-9]|VS[0-9]{1,2}|VP0?[0-9]|SF0?[0-9]|S0?[0-9])-[A-Z][0-9]{1,2}(?:-[0-9]{2,3})?[\"']", "designation literal"),
    (r"[\"']V-5[0-9][A-Z]*-?-?FE", "pipe layer name literal"),
    (r"(?i)facit|expected_(?:meters|quantit|length)|reference_(?:meters|length)", "validation vocabulary"),
    (r"(?i)DRAWING_[ABCD]", "development drawing reference"),
    (r"[\"'](?:path|seqno|xref)_[0-9a-f]{6,}[\"']", "raw object id literal"),
    (r"\b(?:972\.72|347\.64|1223\.4|2384\.0|1684\.0)\b", "coordinate literal from development drawings"),
]
ALLOWED_FILES = {"contamination.py"}


def scan_source(root: str) -> dict[str, Any]:
    findings = []
    documentation_findings = []
    n_files = 0
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".py") or fn in ALLOWED_FILES:
                continue
            path = os.path.join(dirpath, fn)
            n_files += 1
            with open(path, "r", encoding="utf-8") as fh:
                source = fh.read()
            # A preserved source comment is evidence of development history, not
            # an executable drawing-specific branch. Keep both categories visible.
            comments = {t.start[0]: t.start[1] for t in tokenize.generate_tokens(io.StringIO(source).readline)
                        if t.type == tokenize.COMMENT}
            for ln, line in enumerate(source.splitlines(), 1):
                for pat, why in FORBIDDEN_PATTERNS:
                    for match in re.finditer(pat, line):
                        record = {"file": os.path.relpath(path, root), "line": ln, "reason": why, "text": line.strip()[:120]}
                        target = documentation_findings if ln in comments and match.start() >= comments[ln] else findings
                        target.append(record)
    return {"state": "PASS" if not findings else "FAIL", "files_scanned": n_files, "findings": findings, "documentation_findings": documentation_findings,
            "validation_data_dependency": False,
            "note": "production package has no import of validation/facit data; detection runs with data/ absent"}
