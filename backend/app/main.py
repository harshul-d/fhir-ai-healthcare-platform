import json
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.search import search
from backend.app.store import get_bundle, get_summary_by_mrn

app = FastAPI(title="EHR Media Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchQuery(BaseModel):
    query: str
    resource_type: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    top_k: int = 5


@app.get("/")
def health():
    return {"status": "ok", "service": "EHR Media Intelligence API"}


@app.post("/search")
def search_endpoint(q: SearchQuery):
    results = search(
        q.query,
        resource_type=q.resource_type,
        start_date=q.start_date,
        end_date=q.end_date,
        top_k=q.top_k,
    )
    return {"query": q.query, "count": len(results), "results": results}


@app.get("/patient/{mrn}")
def patient_detail(mrn: str):
    """Full AI summary + linked FHIR resources for the detail modal."""
    row = get_bundle(mrn)
    if not row:
        return {"error": "not found", "mrn": mrn}

    bundle = json.loads(row["bundle_json"])
    resources = []
    for entry in bundle.get("entry", []):
        r = entry.get("resource", {})
        resources.append({
            "resource_type": r.get("resourceType"),
            "id": r.get("id"),
            "date": r.get("date") or r.get("effectiveDateTime") or r.get("birthDate") or "",
        })

    summary_json = get_summary_by_mrn(mrn)
    summary = json.loads(summary_json) if summary_json else None
    return {"mrn": mrn, "name": row["patient_name"], "summary": summary, "resources": resources}