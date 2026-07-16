"""
schemas.py — Pydantic models for the RAG Data Generation pipeline.

All output_schema targets for LlmAgents are defined here.
These schemas enforce strict JSON structure on LLM outputs and define
the ground-truth normalized disposition record format.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceType(str, Enum):
    """Channel / source that produced the raw disposition data."""
    call_transcript = "call_transcript"
    ivr_result_code = "ivr_result_code"
    csr_note = "csr_note"
    web_form = "web_form"


class CareGapStatus(str, Enum):
    """Normalized outcome for the care gap after processing the disposition."""
    closed = "closed"
    attempted_not_closed = "attempted_not_closed"
    open_no_contact = "open_no_contact"
    invalid = "invalid"


class ValidationStatus(str, Enum):
    """Set by the SME Validator Agent during quality review."""
    valid = "valid"         # record passed all checks unchanged
    corrected = "corrected" # record had issues; SME agent fixed them
    rejected = "rejected"   # record is fundamentally unusable


# ---------------------------------------------------------------------------
# Core Record
# ---------------------------------------------------------------------------

class DispositionRecord(BaseModel):
    """
    Single normalized disposition record with embedded ground-truth label.

    raw_payload holds the verbatim synthetic input (transcript, IVR JSON, CSR note,
    or web-form JSON). All other fields are the expected normalized output that
    a production ingestion agent should produce from raw_payload.
    """

    record_id: str = Field(
        description="Unique record identifier, format REC-XXXXXX (6-digit zero-padded)"
    )
    source_type: SourceType = Field(
        description="Channel that produced the raw data"
    )
    raw_payload: str = Field(
        description=(
            "Verbatim synthetic input. "
            "call_transcript: multi-turn dialogue with AGENT:/MEMBER: turns + bracketed summary. "
            "ivr_result_code: JSON-like IVR event object. "
            "csr_note: 1-4 sentence free-text CSR note. "
            "web_form: JSON-like web portal submission object."
        )
    )
    member_id: str = Field(
        description="Health plan member ID, format MBR00001–MBR00200"
    )
    provider_id: Optional[str] = Field(
        default=None,
        description="Provider ID (format PRV0001–PRV0050) or null if not referenced"
    )
    care_gap_id: str = Field(
        description=(
            "Specific care-gap identifier from the corpus: "
            "AWC, CBP, CDC-H, COA, COL, FUH, MRP, OMW, SPC, TRC"
        )
    )
    hedis_measure: str = Field(
        description=(
            "Top-level HEDIS measure abbreviation matching the corpus: "
            "AWC, CBP, CDC-H, COA, COL, FUH, MRP, OMW, SPC, TRC"
        )
    )
    responded: bool = Field(
        description="True if member was reached and had any interaction; False if no contact"
    )
    response_summary: str = Field(
        description="Plain-language description of what the member said or did"
    )
    action_taken: str = Field(
        description=(
            "Canonical action from disposition_codes corpus. Valid values: "
            "already_completed, already_completed_unverified, scheduled_appt, refused, "
            "left_voicemail, no_action, callback_requested, language_barrier, "
            "wrong_number, opted_out, opted_out_sms, excluded, pending_followup, "
            "partial_web_submission, web_self_report, engaged_sms, mail_delivered"
        )
    )
    care_gap_status: CareGapStatus = Field(
        description="Normalized outcome for the care gap"
    )
    disposition_code: str = Field(
        description=(
            "Canonical disposition code from the corpus. Valid values: "
            "DISP-CLOSED, DISP-SCHED, DISP-COMP-UV, DISP-REFUS, DISP-VM, "
            "DISP-NOCON, DISP-LANG, DISP-WN, DISP-ADDR, DISP-OPTOUT, "
            "DISP-CB, DISP-EXCL, DISP-PEND, DISP-WEB-PART, DISP-WEB-COMP"
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Extraction confidence 0.0–1.0. "
            "Use 0.85–0.99 for unambiguous cases; 0.50–0.75 for ambiguous/tricky ones"
        )
    )
    validation_status: ValidationStatus = Field(
        default=ValidationStatus.valid,
        description="Set by SME Validator Agent; leave as 'valid' during generation"
    )
    validation_notes: str = Field(
        default="",
        description="SME validation notes; empty string during generation"
    )


# ---------------------------------------------------------------------------
# Agent 1 output: Generated Dataset
# ---------------------------------------------------------------------------

class GeneratedDataset(BaseModel):
    """Output schema for generate_data_agent → state['generated_data']."""

    records: List[DispositionRecord] = Field(
        description="Array of synthetic disposition records with ground-truth labels"
    )
    batch_id: str = Field(
        description="Unique batch ID, format BATCH-YYYYMMDD-HHMMSS"
    )
    generated_at: str = Field(
        description="ISO-8601 UTC datetime of generation"
    )
    batch_size: int = Field(
        description="Number of records in this batch (must match len(records))"
    )


# ---------------------------------------------------------------------------
# Agent 2 output: Validated Dataset
# ---------------------------------------------------------------------------

class ValidatedDataset(BaseModel):
    """Output schema for sme_validator_agent → state['validated_data']."""

    records: List[DispositionRecord] = Field(
        description="All records with updated validation_status and validation_notes"
    )
    batch_id: str = Field(
        description="Same batch_id from the generated dataset"
    )
    validated_at: str = Field(
        description="ISO-8601 UTC datetime of validation"
    )
    total_records: int
    valid_count: int = Field(description="Records with validation_status='valid'")
    corrected_count: int = Field(description="Records with validation_status='corrected'")
    rejected_count: int = Field(description="Records with validation_status='rejected'")


# ---------------------------------------------------------------------------
# Agent 3 output: Dataset Summary
# ---------------------------------------------------------------------------

class SourceTypeDistribution(BaseModel):
    """Breakdown of records by source channel."""
    call_transcript: int = 0
    ivr_result_code: int = 0
    csr_note: int = 0
    web_form: int = 0


class OutcomeDistribution(BaseModel):
    """Breakdown of records by care-gap closure outcome."""
    closed: int = 0
    attempted_not_closed: int = 0
    open_no_contact: int = 0
    invalid: int = 0


class MeasureDistribution(BaseModel):
    """Breakdown of records by HEDIS measure."""
    AWC: int = 0
    CBP: int = 0
    CDC_H: int = Field(default=0, alias="CDC-H")
    COA: int = 0
    COL: int = 0
    FUH: int = 0
    MRP: int = 0
    OMW: int = 0
    SPC: int = 0
    TRC: int = 0

    model_config = {"populate_by_name": True}


class DatasetSummary(BaseModel):
    """Output schema for summary_generator_agent → state['dataset_summary']."""

    batch_id: str
    total_records: int
    by_source_type: SourceTypeDistribution
    by_care_gap_measure: MeasureDistribution
    by_disposition_outcome: OutcomeDistribution
    validation_pass_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="(valid_count + corrected_count) / total_records"
    )
    notable_edge_cases: List[str] = Field(
        description=(
            "List of strings describing edge-case records. "
            "Format each as: 'REC-XXXXXX: <brief description of the edge case>'"
        )
    )
    summary_notes: str = Field(
        description="2-3 sentence narrative about dataset quality and distribution"
    )
