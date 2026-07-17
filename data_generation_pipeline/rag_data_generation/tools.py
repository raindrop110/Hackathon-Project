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


def reload_corpus() -> dict[str, Any]:
    """Force a fresh read of every corpus file, bypassing the in-process cache.

    Needed because learned_patterns.json can change between generation runs
    within the same long-lived process (see append_learned_pattern below) —
    the plain cached _get_corpus() would keep serving a stale snapshot.
    """
    global _corpus_cache
    _corpus_cache = None
    return _get_corpus()


# ---------------------------------------------------------------------------
# Learned-pattern persistence — the feedback half of the upload → corpus →
# generation loop. pattern_extractor_agent (see agent.py) decides whether an
# uploaded file demonstrates something new; if so, the caller persists it here
# so every future generation run (not just the next one) can draw on it.
# ---------------------------------------------------------------------------

_LEARNED_PATTERNS_PATH = _CORPUS_DIR / "learned_patterns.json"
_MAX_LEARNED_PATTERNS_IN_PROMPT = 40


def learned_pattern_count() -> int:
    """Number of patterns persisted so far — used to mint the next pattern_id."""
    if not _LEARNED_PATTERNS_PATH.exists():
        return 0
    with open(_LEARNED_PATTERNS_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    return len(data.get("patterns", []))


def append_learned_pattern(pattern: dict[str, Any]) -> dict[str, Any]:
    """Append one extracted pattern to corpus/learned_patterns.json and invalidate
    the cache so the next build_corpus_context(force_reload=True) picks it up."""
    if _LEARNED_PATTERNS_PATH.exists():
        with open(_LEARNED_PATTERNS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = {"patterns": []}

    data.setdefault("patterns", []).append(pattern)

    with open(_LEARNED_PATTERNS_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    global _corpus_cache
    _corpus_cache = None

    return pattern


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

def build_corpus_context(force_reload: bool = False) -> str:
    """
    Return the full corpus serialised as a formatted JSON string.

    This string is injected into the `instruction` of schema-constrained agents
    (generate_data_agent, sme_validator_agent) at module load time, giving those
    agents all reference data without needing a live tool call.

    force_reload=True bypasses the cache — used by the upload-driven generation
    loop (pipeline_runner.py) so a pattern learned moments ago from a fresh
    upload is visible to the very next generation run, not just the one after
    the process restarts.

    When swapping to Vertex AI RAG, remove calls to this function from agent.py
    and instead attach `retrieve_reference_tool` (or `vertex_rag_tool`) directly
    to the agents (after also removing their `output_schema` or splitting into
    a retriever + schema agent pair).
    """
    corpus = reload_corpus() if force_reload else _get_corpus()

    learned = corpus.get("learned_patterns")
    if learned and len(learned.get("patterns", [])) > _MAX_LEARNED_PATTERNS_IN_PROMPT:
        # Keep the full history on disk; only cap what we inject into the prompt
        # so the corpus context doesn't grow unbounded as uploads accumulate.
        corpus = {
            **corpus,
            "learned_patterns": {
                **learned,
                "patterns": learned["patterns"][-_MAX_LEARNED_PATTERNS_IN_PROMPT:],
            },
        }

    raw = json.dumps(corpus, indent=2, ensure_ascii=False)
    # ADK's inject_session_state replaces every {variable} pattern in instruction
    # strings with session-state lookups.  The corpus JSON contains many {…}
    # delimiters (structural braces AND template strings like {MEASURE_ID}) that
    # must not be treated as state references.  Replace ASCII curly braces with
    # visually identical full-width Unicode variants (U+FF5B / U+FF5D) that the
    # LLM reads correctly but ADK's regex /{+[^{}]*}+/ will not match.
    return raw.replace("{", "｛").replace("}", "｝")
