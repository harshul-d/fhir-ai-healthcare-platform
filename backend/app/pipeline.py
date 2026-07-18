from backend.app.ingest import load_raw, clean_records
from backend.app.fhir_map import build_bundle
from backend.app.store import init_db, save_bundle
from backend.app.summarize import summarize_patient

INPUTS = ["backend/data/patients.json", "backend/data/scanned_notes.csv"]


def run():
    init_db()
    patients = clean_records(load_raw(*INPUTS))
    full_report = []
    for i, p in enumerate(patients):
        bundle, report = build_bundle(p, i)
        save_bundle(p.mrn, p.full_name, bundle.model_dump_json())
        summary = summarize_patient(p)          # generated + cached
        full_report.extend(report)
        print(f"  {p.mrn} {p.full_name}: summary via {summary['source']} (cached={summary['cached']})")

    ok = sum(1 for r in full_report if r["status"] == "ok")
    errs = [r for r in full_report if r["status"] == "error"]
    print(f"Patients: {len(patients)} | Resources valid: {ok} | Errors: {len(errs)}")
    print("Saved bundles + summaries to backend/ehr.sqlite")


if __name__ == "__main__":
    run()