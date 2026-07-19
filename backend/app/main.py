from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.search import search
from backend.app.store import get_bundle

app = FastAPI(title="EHR Media Intelligence API")

# allow the frontend (opened as a local file / different port) to call us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchQuery(BaseModel):
    query: str
    resource_type: Optional[str] = None
    start_date: Optional[str] = None      # "YYYY-MM-DD"
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
    """Full bundle for the patient-detail drawer in the UI."""
    bundle = get_bundle(mrn)
    if not bundle:
        return {"error": "not found", "mrn": mrn}
    return bundle