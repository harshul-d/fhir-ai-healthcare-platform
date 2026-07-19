import chromadb

CHROMA_PATH = "backend/chroma_path"
_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection("ehr", metadata={"hnsw:space": "cosine"})


def index_patients(patients):
    """Embed each patient's records + AI summary into the vector store."""
    from backend.app.summarize import summarize_patient
    col = get_collection()
    model = get_model()

    ids, docs, metas = [], [], []
    for p in patients:
        summary = summarize_patient(p)
        ids.append(f"{p.mrn}-summary")
        docs.append(summary["summary_text"])
        metas.append({
            "mrn": p.mrn, "name": p.full_name, "resource_type": "Summary",
            "record_date": "", "date_int": 0, "snippet": summary["summary_text"][:180],
        })
        for d in p.documents:
            text = f"{d.title or ''} {d.text}".strip()
            date_int = int(d.record_date.strftime("%Y%m%d")) if d.record_date else 0
            ids.append(f"{p.mrn}-{d.doc_id}")
            docs.append(text)
            metas.append({
                "mrn": p.mrn, "name": p.full_name, "resource_type": d.fhir_category,
                "record_date": str(d.record_date or ""), "date_int": date_int,
                "snippet": text[:180],
            })

    embeddings = model.encode(docs).tolist()
    col.upsert(ids=ids, documents=docs, embeddings=embeddings, metadatas=metas)
    return col.count()


def _date_to_int(value):
    """Turn 'YYYY-MM-DD' into an int; ignore junk/empty/'string' input."""
    if not value:
        return None
    digits = str(value).replace("-", "").strip()
    if len(digits) == 8 and digits.isdigit():
        return int(digits)
    return None


def search(query, resource_type=None, start_date=None, end_date=None, top_k=5):
    """Return top-k record matches with relevance scores, with optional filters."""
    col = get_collection()
    model = get_model()
    q_emb = model.encode([query]).tolist()

    conditions = []
    if resource_type and resource_type.strip().lower() not in {"", "string"}:
        conditions.append({"resource_type": resource_type})
    start_int = _date_to_int(start_date)
    end_int = _date_to_int(end_date)
    if start_int is not None:
        conditions.append({"date_int": {"$gte": start_int}})
    if end_int is not None:
        conditions.append({"date_int": {"$lte": end_int}})

    where = None
    if len(conditions) == 1:
        where = conditions[0]
    elif len(conditions) > 1:
        where = {"$and": conditions}

    res = col.query(query_embeddings=q_emb, n_results=top_k, where=where)
    metas = res["metadatas"][0]
    dists = res["distances"][0]
    return [{**m, "relevance": round(1 - dist, 3)} for m, dist in zip(metas, dists)]