"""
schemas.py — Pydantic output schema for the test_comparison_agent pipeline.

generation_quality_agent scores an ENTIRE batch of synthetic disposition records
(from the data generation pipeline) against ONE real disposition summary (from
disposition_normalization's summarization stage) — a heatmap of "how well does
the generator's output resemble real production data?"
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class HeatmapCell(BaseModel):
    """One synthetic record's alignment scores against the real reference summary."""

    record_id: str = Field(description="The synthetic record's record_id")
    source_type: str = Field(description="call_transcript | ivr_result_code | csr_note | web_form")
    measure_alignment: float = Field(ge=0.0, le=100.0)
    channel_alignment: float = Field(ge=0.0, le=100.0)
    disposition_plausibility: float = Field(ge=0.0, le=100.0)
    confidence_calibration: float = Field(ge=0.0, le=100.0)
    structural_realism: float = Field(ge=0.0, le=100.0)
    overall: float = Field(ge=0.0, le=100.0, description="Mean of the 5 dimension scores")
    notes: str = Field(default="", description="1 short sentence on this record's standout strength/weakness")


class GenerationQualityReport(BaseModel):
    """Output schema for generation_quality_agent -> state['generation_quality_report'].

    Compares ONE real disposition summary against an ENTIRE batch of synthetic
    records, to answer: how well does the data generator's output resemble real
    production data? Rendered by the frontend as a dimension x record heatmap.
    """

    batch_id: str = Field(description="batch_id of the synthetic batch being scored")
    reference_record_id: str = Field(
        description="member_id or gap_id of the real record used as the reference"
    )
    dimensions: List[str] = Field(
        description=(
            "The 5 dimension names in display order: measure_alignment, "
            "channel_alignment, disposition_plausibility, confidence_calibration, "
            "structural_realism — for the frontend heatmap's rows"
        )
    )
    cells: List[HeatmapCell] = Field(
        description="One entry per synthetic record in the batch — the heatmap's columns"
    )
    overall_score: float = Field(ge=0.0, le=100.0, description="Mean of all cells' overall scores")
    strongest_dimension: str = Field(description="Which of the 5 dimensions scored highest on average")
    weakest_dimension: str = Field(description="Which of the 5 dimensions scored lowest on average")
    narrative: str = Field(
        description=(
            "3-4 sentence analysis of what this run reveals about generator quality — "
            "strong across the board, struggles with a particular dimension or source "
            "type, etc."
        )
    )
