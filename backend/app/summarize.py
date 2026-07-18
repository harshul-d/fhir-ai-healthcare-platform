import hashlib
import json
import os

from backend.app.models import CleanPatient

DISCLAIMER = "AI-generated summary. Not a clinical decision. Verify against source records."
ANOMALY_WORDS = ["elevated", "high", "flagged", "abnormal", "low", "cardiomegaly", "acute"]


def cache_key(p: CleanPatient) -> str:
    """Keyed by patient MRN + a hash of their record content, so re-runs hit cache."""
    blob = p.mrn + "|" + "|".join(
        f"{d.doc_id}:{d.record_date}:{d.text}" for d in p.documents
    )
    return p.mrn + "-" + hashlib.md5(blob.encode()).hexdigest()[:12]


def _extract_facts(p: CleanPatient) -> dict:
    diagnoses, media, anomalies = [], [], []
    for d in p.documents:
        label = d.title or d.type
        if d.type in {"imaging", "lab"}:
            media.append(f"{label} ({d.record_date or 'undated'})")
        else:
            diagnoses.append(label)
        low = d.text.lower()
        for w in ANOMALY_WORDS:
            if w in low:
                anomalies.append(f"{label}: '{w}' noted")
                break
    return {"diagnoses": diagnoses, "media": media, "anomalies": anomalies}


def _summarize_mock(p: CleanPatient) -> dict:
    facts = _extract_facts(p)
    chief = facts["media"][0] if facts["media"] else (facts["diagnoses"][0] if facts["diagnoses"] else "No documented concern")
    text = (
        f"{p.full_name} (MRN {p.mrn}) has {len(p.documents)} record(s) on file. "
        f"Chief concern relates to {chief}. "
        f"Recent media: {', '.join(facts['media']) or 'none'}. "
        f"Notable findings: {', '.join(facts['anomalies']) or 'none flagged'}."
    )
    return {
        "chief_concern": chief,
        "key_diagnoses": facts["diagnoses"] or ["None documented"],
        "recent_media": facts["media"] or ["None"],
        "flagged_anomalies": facts["anomalies"] or ["None flagged"],
        "summary_text": text,
        "source": "mock",
        "confidence": "low (rule-based, no LLM)",
        "disclaimer": DISCLAIMER,
    }


def _summarize_via_claude(p: CleanPatient) -> dict:
    import anthropic
    facts = _extract_facts(p)
    record_text = "\n".join(
        f"- [{d.type}] {d.title or ''} ({d.record_date or 'undated'}): {d.text}"
        for d in p.documents
    )
    prompt = (
        f"Patient {p.full_name}, MRN {p.mrn}. Records:\n{record_text}\n\n"
        "Return ONLY JSON with keys: chief_concern (string), key_diagnoses (list), "
        "recent_media (list), flagged_anomalies (list), summary_text (string, under 200 words). "
        "Be clinically accurate. No preamble, no markdown fences."
    )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-sonnet-4-5",   # change if your key needs a different model
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip().strip("`")
    if raw.startswith("json"):
        raw = raw[4:].strip()
    data = json.loads(raw)
    data.update({"source": "claude", "confidence": "medium (LLM-generated)", "disclaimer": DISCLAIMER})
    return data


def summarize_patient(p: CleanPatient) -> dict:
    from backend.app.store import get_summary, save_summary
    key = cache_key(p)
    cached = get_summary(key)
    if cached:
        result = json.loads(cached)
        result["cached"] = True
        return result

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            result = _summarize_via_claude(p)
        except Exception as e:
            result = _summarize_mock(p)
            result["note"] = f"Claude call failed, used mock: {e}"
    else:
        result = _summarize_mock(p)

    save_summary(key, p.mrn, json.dumps(result))
    result["cached"] = False
    return result