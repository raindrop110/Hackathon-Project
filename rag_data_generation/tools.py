"""
tools.py — Retrieval tool for the RAG Data Generation pipeline.

ARCHITECTURE DECISION — output_schema vs. Tools
================================================
ADK's LlmAgent raises a validation error if both `output_schema` and `tools` are set
on the same agent (Gemini's controlled-generation / JSON-mode is incompatible with
parallel function-calling in the same turn).

Resolution chosen: **pre-load retrieval at module import time**.
  1. `retrieve_reference()` is implemented as a real FunctionTool (ready to attach to
     any tool-using agent).
  2. At module load time, `build_corpus_context()` calls retrieve_reference("all") and
     serialises the full corpus to a JSON string.
  3. That string is injected directly into each schema-constrained agent's `instruction`
     parameter, so the LLM has all reference data without needing a tool call.

SWAP SEAM (clearly marked below):
  When a Vertex AI RAG Engine corpus is ready, replace the body of
  `retrieve_reference_raw()` with a `VertexAiRagRetrieval` tool call or SDK query.
  The rest of the pipeline requires zero changes.
"""

import json
from pathlib import Path
from typing import Any

from google.adk.tools import FunctionTool

# ---------------------------------------------------------------------------
# Corpus loader — reads local JSON files from rag_data_generation/corpus/
# ---------------------------------------------------------------------------

_CORPUS_DIR = Path(__file__).parent / "corpus"
_corpus_cache: dict[str, Any] | None = None


def _load_corpus() -> dict[str, Any]:
    """Load all JSON files from the local corpus directory into a dict keyed by stem."""
    corpus: dict[str, Any] = {}
    for filepath in sorted(_CORPUS_DIR.glob("*.json")):
        with open(filepath, encoding="utf-8") as fh:
            corpus[filepath.stem] = json.load(fh)
    return corpus


def _get_corpus() -> dict[str, Any]:
    """Return the cached corpus, loading it on first call."""
    global _corpus_cache
    if _corpus_cache is None:
        _corpus_cache = _load_corpus()
    return _corpus_cache


# ---------------------------------------------------------------------------
# Core retrieval function — THIS IS THE SWAP SEAM
# ---------------------------------------------------------------------------

def retrieve_reference_raw(topic: str) -> dict:
    """
    Retrieve reference data from the knowledge corpus.

    Supported topics:
      - "hedis_measures"       : HEDIS measure specs, denominators, numerators
      - "ivr_codes"            : IVR / SMS / Mail result code dictionary
      - "disposition_codes"    : Canonical normalized disposition codes
      - "care_gap_definitions" : Care-gap closure rules, edge-case guidance
      - "all"                  : Full corpus (all topics merged)

    ╔══════════════════════════════════════════════════════════════════╗
    ║  SWAP SEAM — replace this function body with Vertex AI RAG:     ║
    ║                                                                  ║
    ║  from google.adk.tools.retrieval import VertexAiRagRetrieval    ║
    ║                                                                  ║
    ║  vertex_rag_tool = VertexAiRagRetrieval(                        ║
    ║      name="retrieve_reference",                                  ║
    ║      description="Retrieve HEDIS specs, IVR codes, and          ║
    ║                    disposition definitions from Vertex AI RAG",  ║
    ║      rag_corpus="projects/{PROJECT_ID}/locations/{REGION}/"     ║
    ║                 "ragCorpora/{CORPUS_ID}",                       ║
    ║      similarity_top_k=5,                                        ║
    ║      vector_distance_threshold=0.5,                             ║
    ║  )                                                               ║
    ║  # Then attach vertex_rag_tool to tool-using agents and         ║
    ║  # remove the pre-load injection from agent.py instructions.    ║
    ╚══════════════════════════════════════════════════════════════════╝
    """
    corpus = _get_corpus()
    if topic == "all":
        return corpus
    result = corpus.get(topic)
    if result is None:
        return {
            "error": f"Topic '{topic}' not found.",
            "available_topics": list(corpus.keys()),
        }
    return result


def retrieve_reference(topic: str) -> dict:
    """
    Retrieve reference knowledge for healthcare care-gap disposition data.

    Use this tool to look up HEDIS measure specifications, valid IVR result codes,
    canonical disposition codes, and care-gap closure rules before generating or
    validating synthetic records.

    Args:
        topic: One of 'hedis_measures', 'ivr_codes', 'disposition_codes',
               'care_gap_definitions', or 'all' for the complete corpus.

    Returns:
        dict: The requested reference data as a structured dictionary.
    """
    return retrieve_reference_raw(topic)


# ADK FunctionTool wrapper — attach to any non-schema-constrained agent
retrieve_reference_tool = FunctionTool(func=retrieve_reference)


# ---------------------------------------------------------------------------
# Helper used by agent.py to pre-load corpus into instruction strings
# ---------------------------------------------------------------------------

def build_corpus_context() -> str:
    """
    Return the full corpus serialised as a formatted JSON string.

    This string is injected into the `instruction` of schema-constrained agents
    (generate_data_agent, sme_validator_agent) at module load time, giving those
    agents all reference data without needing a live tool call.

    When swapping to Vertex AI RAG, remove calls to this function from agent.py
    and instead attach `retrieve_reference_tool` (or `vertex_rag_tool`) directly
    to the agents (after also removing their `output_schema` or splitting into
    a retriever + schema agent pair).
    """
    return json.dumps(retrieve_reference_raw("all"), indent=2, ensure_ascii=False)
