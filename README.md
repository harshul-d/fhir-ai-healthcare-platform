# EHR Media Intelligence Platform

An AI-powered pipeline that ingests messy EHR data, normalizes it to HL7 FHIR (R4B),
generates clinical summaries, and exposes a semantic search UI for clinicians.

## What it does

1. **Ingest & clean** — reads JSON + CSV EHR exports, fixes inconsistent dates, normalizes
   MRNs and gender codes, dedupes/merges duplicate patients, and logs every change to a per-record audit trail.
2. **FHIR mapping** — maps clean records to `Patient`, `Encounter`, `DocumentReference`, and
   `DiagnosticReport` resources, bundles them per patient, validates against the FHIR schema, and stores them in SQLite.
3. **AI summaries** — generates a structured clinical summary per patient (chief concern, diagnoses,
   media, anomalies) with a disclaimer field. Cached by patient + record hash. Uses Claude if an API
   key is set, otherwise a deterministic rule-based fallback.
4. **Semantic search** — embeds all records + summaries with `all-MiniLM-L6-v2` into a Chroma vector
   store; a `POST /search` endpoint returns ranked matches with relevance scores and supports resource-type / date filters.
5. **Frontend** — a Tailwind UI with a search bar, ranked result cards, a patient-detail modal, filters,
   loading/empty states, and accessible markup.

## Tech stack

Python 3.11+ · FastAPI · Pydantic v2 · fhir.resources (R4B) · sentence-transformers · ChromaDB · SQLite · pytest · Tailwind CSS · Vanilla JS

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# 2. Install dependencies
pip install -r backend/requirements.txt
```

## Running it

```bash
# 1. Run the full pipeline: ingest -> clean -> FHIR -> summarize -> store
python -m backend.app.pipeline

# 2. Build the search index
python -c "from backend.app.ingest import load_raw, clean_records; from backend.app.store import init_db; from backend.app.search import index_patients; init_db(); index_patients(clean_records(load_raw('backend/data/patients.json','backend/data/scanned_notes.csv')))"

# 3. Start the API
uvicorn backend.app.main:app --reload
# API docs at http://127.0.0.1:8000/docs
```

Then open `frontend/index.html` in a browser and search.

## Optional: real LLM summaries

By default, summaries use a rule-based fallback (no key needed). To use Claude, set an
environment variable before running the pipeline:

```bash
# Windows: $env:ANTHROPIC_API_KEY="your-key"
# macOS/Linux: export ANTHROPIC_API_KEY="your-key"
```

## Tests

```bash
python -m pytest
```

## Design decisions

- **R4B instead of R4** — the `fhir.resources` library dropped the standalone R4 package; R4B is
  the current equivalent and validates cleanly against the same resource types.
- **Merge on canonical MRN, flag identifier conflicts** — records with the same normalized MRN are
  merged; conflicting DOBs on the same MRN are logged rather than silently overwritten.
- **Local embeddings** — `all-MiniLM-L6-v2` runs offline, keeping the demo self-contained and free.
- **LLM fallback** — the summarizer works with no API key so the project is reproducible out of the box.

## Note

All data in this repo is synthetic. No real patient data is included.