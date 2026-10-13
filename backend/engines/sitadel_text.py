"""Repair source encoding only; retain the exact original for each changed field."""
from ftfy import fix_encoding

SOURCE_FIELDS = ("ADR_LOCALITE_TER", "ADR_LIBVOIE_TER", "ADR_LIEUDIT_TER")


def repair_source_row(row):
    fixed, changes = dict(row), {}
    for field in SOURCE_FIELDS:
        value = row.get(field)
        if not isinstance(value, str):
            continue
        corrected = fix_encoding(value)
        if corrected != value:
            fixed[field] = corrected
            changes[field] = {"raw": value, "corrected": corrected}
    return fixed, changes


def repair_cached_address(permit):
    changes = dict(permit.get("source_text_corrections") or {})
    for field in ("adresse", "adresse_complement", "commune"):
        value = permit.get(field)
        if isinstance(value, str):
            corrected = fix_encoding(value)
            if corrected != value:
                permit[field] = corrected
                changes[field] = {"raw": value, "corrected": corrected}
    permit["source_text_corrections"] = changes