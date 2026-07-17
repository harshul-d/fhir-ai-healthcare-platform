from datetime import date
from backend.app.ingest import clean_records, normalize_mrn, parse_date


def test_date_format_normalization():
    for raw, expected in [
        ("2024-07-01", date(2024, 7, 1)),
        ("06/20/2024", date(2024, 6, 20)),
        ("20240515", date(2024, 5, 15)),
        ("12 June 1985", date(1985, 6, 12)),
    ]:
        parsed, _ = parse_date(raw)
        assert parsed == expected, raw


def test_gender_and_mrn_normalization():
    recs = clean_records([{"mrn": "mrn 0001", "gender": "F", "dob": "1985-06-12", "documents": []}])
    assert recs[0].mrn == "MRN0001"
    assert recs[0].gender == "female"


def test_duplicate_merge_by_canonical_mrn():
    raw = [
        {"mrn": "MRN-0001", "dob": "1985-06-12", "gender": "F",
         "documents": [{"id": "d1", "type": "lab", "date": "2024-01-01", "text": "a"}]},
        {"mrn": "mrn 0001", "dob": "1985-06-12", "gender": "female",
         "documents": [{"id": "d2", "type": "imaging", "date": "2024-02-01", "text": "b"}]},
    ]
    recs = clean_records(raw)
    assert len(recs) == 1
    assert len(recs[0].documents) == 2


def test_missing_mrn_gets_default_and_audit():
    recs = clean_records([{"mrn": "", "dob": "2000-01-01", "documents": []}])
    assert recs[0].mrn.startswith("UNKNOWN")
    assert any(a.action == "filled_default" for a in recs[0].audit)


def test_conflicting_dob_is_flagged():
    raw = [
        {"mrn": "MRN-0009", "dob": "1990-01-01", "documents": []},
        {"mrn": "MRN-0009", "dob": "1991-01-01", "documents": []},
    ]
    recs = clean_records(raw)
    assert any(a.action == "conflict" for a in recs[0].audit)