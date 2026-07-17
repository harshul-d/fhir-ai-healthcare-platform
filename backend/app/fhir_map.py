import base64
import re
from datetime import datetime, timezone

from pydantic import ValidationError

from fhir.resources.R4B.patient import Patient
from fhir.resources.R4B.encounter import Encounter
from fhir.resources.R4B.documentreference import DocumentReference
from fhir.resources.R4B.diagnosticreport import DiagnosticReport
from fhir.resources.R4B.bundle import Bundle

from backend.app.models import CleanPatient

MODEL_MAP = {
    "Patient": Patient,
    "Encounter": Encounter,
    "DocumentReference": DocumentReference,
    "DiagnosticReport": DiagnosticReport,
}


def fhir_id(raw) -> str:
    """FHIR ids allow only A-Z a-z 0-9 - . (max 64 chars)."""
    s = re.sub(r"[^A-Za-z0-9\-\.]", "-", str(raw))[:64]
    return s or "unknown"


def _instant(d):
    if d is None:
        return None
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat()


def _b64(text: str) -> str:
    return base64.b64encode((text or "").encode()).decode()


def _patient_dict(p: CleanPatient, pid: str) -> dict:
    gender = p.gender if p.gender in {"male", "female", "other", "unknown"} else "unknown"
    data = {"resourceType": "Patient", "id": pid, "gender": gender}
    name = {}
    if p.family_name:
        name["family"] = p.family_name
    if p.given_name:
        name["given"] = [p.given_name]
    if name:
        data["name"] = [name]
    if p.birth_date:
        data["birthDate"] = p.birth_date.isoformat()
    return data


def _encounter_dict(pid: str, encid: str) -> dict:
    return {
        "resourceType": "Encounter",
        "id": encid,
        "status": "finished",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "AMB",
            "display": "ambulatory",
        },
        "subject": {"reference": f"Patient/{pid}"},
    }


def _doc_reference_dict(doc, pid, encid, did) -> dict:
    data = {
        "resourceType": "DocumentReference",
        "id": did,
        "status": "current",
        "type": {"text": doc.title or doc.type},
        "subject": {"reference": f"Patient/{pid}"},
        "context": {"encounter": [{"reference": f"Encounter/{encid}"}]},
        "content": [{
            "attachment": {
                "contentType": "text/plain",
                "data": _b64(doc.text),
                "title": doc.title or doc.type,
            }
        }],
    }
    inst = _instant(doc.record_date)
    if inst:
        data["date"] = inst
    return data


def _diag_report_dict(doc, pid, encid, did) -> dict:
    data = {
        "resourceType": "DiagnosticReport",
        "id": did,
        "status": "final",
        "code": {"text": doc.title or doc.type},
        "subject": {"reference": f"Patient/{pid}"},
        "encounter": {"reference": f"Encounter/{encid}"},
        "presentedForm": [{
            "contentType": "text/plain",
            "data": _b64(doc.text),
            "title": doc.title or doc.type,
        }],
    }
    if doc.text:
        data["conclusion"] = doc.text
    if doc.record_date:
        data["effectiveDateTime"] = doc.record_date.isoformat()
    return data


def build_bundle(p: CleanPatient, idx: int):
    """Return (Bundle, validation_report) for one patient."""
    pid = fhir_id(p.mrn) or f"patient-{idx}"
    encid = f"enc-{pid}"

    candidates = [
        ("Patient", pid, _patient_dict(p, pid)),
        ("Encounter", encid, _encounter_dict(pid, encid)),
    ]
    for doc in p.documents:
        did = fhir_id(doc.doc_id)
        if doc.fhir_category == "DiagnosticReport":
            candidates.append(("DiagnosticReport", did, _diag_report_dict(doc, pid, encid, did)))
        else:
            candidates.append(("DocumentReference", did, _doc_reference_dict(doc, pid, encid, did)))

    entries = []
    report = []
    for rtype, rid, data in candidates:
        try:
            MODEL_MAP[rtype].model_validate(data)          # validate against FHIR schema
            entries.append({"fullUrl": f"{rtype}/{rid}", "resource": data})
            report.append({"patient": p.mrn, "resource_type": rtype, "id": rid, "status": "ok"})
        except ValidationError as e:
            first = e.errors()[0] if e.errors() else {"msg": str(e)}
            report.append({"patient": p.mrn, "resource_type": rtype, "id": rid,
                           "status": "error", "error": f"{first.get('loc')}: {first.get('msg')}"})

    bundle = Bundle.model_validate({"resourceType": "Bundle", "type": "collection", "entry": entries})
    return bundle, report


def build_all(patients: list[CleanPatient]):
    """Return (list_of_bundles, combined_validation_report)."""
    bundles, report = [], []
    for i, p in enumerate(patients):
        b, rep = build_bundle(p, i)
        bundles.append(b)
        report.extend(rep)
    return bundles, report