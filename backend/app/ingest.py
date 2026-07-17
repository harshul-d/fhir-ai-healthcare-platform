import csv
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from dateutil import parser as dateutil_parser

from backend.app.models import AuditEntry, CleanDocument, CleanPatient, Gender

EXPLICIT_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d", "%B %d, %Y", "%d %B %Y"]

GENDER_MAP = {
    "m": Gender.male, "male": Gender.male, "1": Gender.male,
    "f": Gender.female, "female": Gender.female, "2": Gender.female,
    "o": Gender.other, "other": Gender.other,
}


def parse_date(raw: Optional[str]) -> tuple[Optional[date], Optional[str]]:
    """Return (date, note). Tries explicit formats first, then a fallback parser."""
    if not raw or not str(raw).strip():
        return None, "missing date"
    raw = str(raw).strip()
    for fmt in EXPLICIT_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date(), None
        except ValueError:
            continue
    try:
        return dateutil_parser.parse(raw, dayfirst=False).date(), "parsed via fallback"
    except (ValueError, OverflowError):
        return None, f"unparseable date: {raw!r}"


def normalize_mrn(raw: str) -> str:
    """Canonical MRN: strip separators/whitespace, uppercase."""
    return re.sub(r"[\s\-_]", "", str(raw)).upper()


def normalize_gender(raw: Optional[str]) -> Gender:
    if raw is None:
        return Gender.unknown
    return GENDER_MAP.get(str(raw).strip().lower(), Gender.unknown)


def _raw_from_json(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text())
    out = []
    for r in data:
        out.append({
            "mrn": r.get("mrn", ""),
            "given_name": r.get("first"),
            "family_name": r.get("last"),
            "dob": r.get("dob"),
            "gender": r.get("sex"),
            "documents": r.get("documents", []),
        })
    return out


def _raw_from_csv(path: Path) -> list[dict]:
    out = []
    with Path(path).open(newline="") as f:
        for row in csv.DictReader(f):
            given, _, family = (row.get("name", "") or "").partition(" ")
            out.append({
                "mrn": row.get("mrn", ""),
                "given_name": given or None,
                "family_name": family or None,
                "dob": row.get("dob"),
                "gender": row.get("gender"),
                "documents": [{
                    "id": f"{row.get('mrn','')}-{row.get('doc_title','doc')}",
                    "type": row.get("doc_type", "note"),
                    "title": row.get("doc_title"),
                    "date": row.get("doc_date"),
                    "text": row.get("note_text", ""),
                }],
            })
    return out


def load_raw(*paths) -> list[dict]:
    """Accept JSON and CSV inputs; dispatch by file extension."""
    raw: list[dict] = []
    for p in paths:
        p = Path(p)
        if p.suffix.lower() == ".json":
            raw += _raw_from_json(p)
        elif p.suffix.lower() in {".csv", ".txt"}:
            raw += _raw_from_csv(p)
        else:
            raise ValueError(f"Unsupported input format: {p.suffix}")
    return raw


def _clean_docs(raw_docs: list[dict], audit: list[AuditEntry]) -> list[CleanDocument]:
    docs = []
    for d in raw_docs:
        parsed, note = parse_date(d.get("date"))
        if note:
            audit.append(AuditEntry(field=f"doc[{d.get('id')}].date", action="normalized",
                                    before=str(d.get("date")), after=str(parsed), note=note))
        docs.append(CleanDocument(
            doc_id=str(d.get("id") or f"doc-{len(docs)}"),
            type=str(d.get("type") or "note"),
            title=d.get("title"),
            record_date=parsed,
            text=str(d.get("text") or ""),
        ))
    return docs


def clean_records(raw: list[dict]) -> list[CleanPatient]:
    """Normalize, dedup by canonical MRN, merge docs, and log every change."""
    by_mrn: dict[str, CleanPatient] = {}

    for r in raw:
        audit: list[AuditEntry] = []

        orig_mrn = str(r.get("mrn", ""))
        mrn = normalize_mrn(orig_mrn)
        if not mrn:
            audit.append(AuditEntry(field="mrn", action="filled_default",
                                    before=orig_mrn, after="UNKNOWN", note="missing MRN"))
            mrn = f"UNKNOWN-{len(by_mrn)}"
        elif mrn != orig_mrn:
            audit.append(AuditEntry(field="mrn", action="normalized", before=orig_mrn, after=mrn))

        birth_date, dob_note = parse_date(r.get("dob"))
        if dob_note:
            audit.append(AuditEntry(field="birth_date", action="normalized",
                                    before=str(r.get("dob")), after=str(birth_date), note=dob_note))

        gender = normalize_gender(r.get("gender"))
        if str(r.get("gender")).strip().lower() != gender.value:
            audit.append(AuditEntry(field="gender", action="normalized",
                                    before=str(r.get("gender")), after=gender.value))

        docs = _clean_docs(r.get("documents", []), audit)

        if mrn in by_mrn:
            existing = by_mrn[mrn]
            if birth_date and existing.birth_date and birth_date != existing.birth_date:
                existing.audit.append(AuditEntry(
                    field="birth_date", action="conflict",
                    before=str(existing.birth_date), after=str(birth_date),
                    note=f"conflicting DOB for MRN {mrn}; kept first"))
            existing.documents.extend(docs)
            existing.audit.append(AuditEntry(field="record", action="deduped",
                                             note=f"merged {len(docs)} doc(s) from duplicate MRN"))
            existing.audit.extend(audit)
        else:
            by_mrn[mrn] = CleanPatient(
                mrn=mrn, given_name=r.get("given_name"), family_name=r.get("family_name"),
                birth_date=birth_date, gender=gender.value, documents=docs, audit=audit,
            )

    return list(by_mrn.values())