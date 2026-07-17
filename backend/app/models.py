from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class Gender(str, Enum):
    male = "male"
    female = "female"
    other = "other"
    unknown = "unknown"


class AuditEntry(BaseModel):
    field: str
    action: str            # normalized | filled_default | deduped | conflict
    before: Optional[str] = None
    after: Optional[str] = None
    note: Optional[str] = None


class CleanDocument(BaseModel):
    doc_id: str
    type: str                       # imaging | lab | discharge_summary | note
    title: Optional[str] = None
    record_date: Optional[date] = None
    text: str = ""

    @property
    def fhir_category(self) -> str:
        # labs/imaging -> DiagnosticReport, everything else -> DocumentReference
        return "DiagnosticReport" if self.type in {"lab", "imaging"} else "DocumentReference"


class CleanPatient(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    mrn: str
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    birth_date: Optional[date] = None
    gender: str = Gender.unknown.value
    documents: list[CleanDocument] = Field(default_factory=list)
    audit: list[AuditEntry] = Field(default_factory=list)

    @property
    def full_name(self) -> str:
        parts = [p for p in (self.given_name, self.family_name) if p]
        return " ".join(parts) or "Unknown"