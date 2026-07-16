"""
schemas.py — Pydantic output schemas for the test_comparison_agent pipeline.

Stage 1 output: TestBatch (generated records with ground-truth labels)
Stage 2 output: NormalizationBatch (normalization agent's output per record)
Stage 3 output: ComparisonReport (accuracy metrics vs ground truth)
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Stage 1 — Test Data Generator output
# ---------------------------------------------------------------------------

class TestRecord(BaseModel):
    """
    Synthetic disposition record with embedded ground-truth labels.
    raw_payload is the verbatim synthetic input the normalizer must interpret.
    All other fields are the CORRECT expected normalized output.
    """
    record_id: str = Field(description="Unique ID, format REC-XXXXXX")
    source_type: str = Field(
        description="call_transcript | ivr_result_code | csr_note | web_form"
    )
    member_id: str = Field(description="MBR00001–MBR00200")
    hedis_measure: str = Field(description="AWC|CBP|CDC-H|COA|COL|FUH|MRP|OMW|SPC|TRC")
    raw_payload: str = Field(description="Verbatim synthetic input the normalizer must process")
    # Ground-truth labels
    care_gap_status: str = Field(
        description="closed | attempted_not_closed | open_no_contact | invalid"
    )
    disposition_code: str = Field(description="DISP-XXX canonical code")
    responded: bool = Field(description="True if member was reached")
    action_taken: str = Field(description="Canonical action from disposition_codes corpus")
    confidence: float = Field(ge=0.0, le=1.0, description="Ground-truth labeling confidence")


class TestBatch(BaseModel):
    """Output schema for test_data_generator → state['ground_truth_data']."""
    batch_id: str = Field(description="BATCH-YYYYMMDD-HHMMSS")
    generated_at: str = Field(description="ISO-8601 UTC datetime")
    batch_size: int
    records: List[TestRecord]


# ---------------------------------------------------------------------------
# Stage 2 — Batch Normalizer output
# ---------------------------------------------------------------------------

class NormalizationResult(BaseModel):
    """Normalization output for a single record, derived from raw_payload only."""
    record_id: str
    confidence: str = Field(description="high | medium | low")
    disposition_code: Optional[str] = Field(
        default=None, description="Normalized DISP-XXX code"
    )
    care_gap_status: Optional[str] = Field(
        default=None,
        description="closed | attempted_not_closed | open_no_contact | invalid"
    )
    responded: Optional[bool] = None
    action_taken: Optional[str] = None


class NormalizationBatch(BaseModel):
    """Output schema for batch_normalizer → state['normalization_results']."""
    batch_id: str
    total_records: int
    records: List[NormalizationResult]


# ---------------------------------------------------------------------------
# Stage 3 — Comparison Report output
# ---------------------------------------------------------------------------

class FieldAccuracy(BaseModel):
    """Accuracy for a single compared field across all records."""
    field_name: str
    correct: int
    total: int
    accuracy_pct: float = Field(ge=0.0, le=100.0)


class SourceTypeAccuracy(BaseModel):
    """Per-source-type accuracy (percentage of records fully correct)."""
    call_transcript: float = Field(default=0.0, ge=0.0, le=100.0)
    ivr_result_code: float = Field(default=0.0, ge=0.0, le=100.0)
    csr_note: float = Field(default=0.0, ge=0.0, le=100.0)
    web_form: float = Field(default=0.0, ge=0.0, le=100.0)


class RecordMismatch(BaseModel):
    """A field mismatch between ground truth and normalization output."""
    record_id: str
    source_type: str
    hedis_measure: str
    field: str
    ground_truth: str
    normalized: str
    normalization_confidence: str  # "high" | "medium" | "low"


class ComparisonReport(BaseModel):
    """Output schema for accuracy_comparator → state['comparison_report']."""
    batch_id: str
    total_records: int

    # Record-level accuracy (a record is "correct" if ALL 4 compared fields match)
    records_fully_correct: int
    record_accuracy_pct: float = Field(ge=0.0, le=100.0)

    # Field-level accuracy breakdown
    field_accuracy: List[FieldAccuracy]

    # Accuracy by source type (percentage of records fully correct per channel)
    accuracy_by_source_type: SourceTypeAccuracy

    # Confidence-stratified accuracy
    high_confidence_record_accuracy_pct: float = Field(ge=0.0, le=100.0)
    low_confidence_record_accuracy_pct: float = Field(ge=0.0, le=100.0)

    # Mismatch details
    total_field_mismatches: int
    mismatches: List[RecordMismatch]

    summary: str = Field(
        description=(
            "3-4 sentence narrative: overall accuracy, which field performed best/worst, "
            "whether low-confidence records skewed accuracy, and key insight about "
            "where the normalization pipeline struggles most."
        )
    )
