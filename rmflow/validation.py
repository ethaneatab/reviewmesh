"""Validation: is the stored document what intake was given, and are the fields usable?"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

MAX_BYTES = 5 * 1024 * 1024
REQUIRED = {"invoice": ("amount", "vendor"), "contract": ("counterparty",), "claim": ("claim_number",), "kyc": ()}


# @learn:validate
def validate(doc_type: str, fields: dict[str, Any], intake_sha256: str | None, seen: dict[str, Any]) -> dict[str, Any]:
    """`seen` is what the Lambda measured on the S3 object (size, sha256, sniffed type)."""
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, issue: str) -> None:
        checks.append({"check": name, "ok": ok, **({} if ok else {"issue": issue})})

    check("file_type", seen.get("sniff") in ("pdf", "csv"), f"unsupported file type {seen.get('sniff')!r}")
    size = int(seen.get("size") or 0)
    check("file_size", 0 < size <= MAX_BYTES, f"size {size} bytes outside 1..{MAX_BYTES}")
    check("integrity", intake_sha256 is None or seen.get("sha256") in (None, intake_sha256),
          "sha256 seen by the Lambda differs from what intake stored")
    missing = [f for f in REQUIRED.get(doc_type, ()) if not str(fields.get(f, "")).strip()]
    check("required_fields", not missing, f"missing fields: {', '.join(missing)}")
    amount = None
    if "amount" in fields:
        try:
            amount = Decimal(str(fields["amount"]))
            check("amount_format", amount >= 0, "amount is negative")
        except InvalidOperation:
            check("amount_format", False, f"amount {fields['amount']!r} is not a number")
    risk = 10
    if amount is not None and amount > 10_000:
        risk += 60
    if missing:
        risk += 30
    if doc_type == "kyc":
        risk += 20
    issues = [c["issue"] for c in checks if not c["ok"]]
    return {"passed": not issues, "issues": issues, "risk_score": min(risk, 100), "checks": checks}
# @learn:end validate
