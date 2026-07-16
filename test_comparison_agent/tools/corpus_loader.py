"""
corpus_loader.py — Loads the reference corpus from rag_data_generation/corpus/.

Re-uses the same JSON files as the data generation pipeline so normalization
rules are identical in both the generator and the comparison normalizer.
"""

import json
from pathlib import Path
from typing import Any

_CORPUS_DIR = (
    Path(__file__).parents[2]
    / "data_generation_pipeline"
    / "rag_data_generation"
    / "corpus"
)

_corpus_cache: dict[str, Any] | None = None


def _load_corpus() -> dict[str, Any]:
    corpus: dict[str, Any] = {}
    for filepath in sorted(_CORPUS_DIR.glob("*.json")):
        with open(filepath, encoding="utf-8") as fh:
            corpus[filepath.stem] = json.load(fh)
    return corpus


def _get_corpus() -> dict[str, Any]:
    global _corpus_cache
    if _corpus_cache is None:
        _corpus_cache = _load_corpus()
    return _corpus_cache


def build_corpus_context() -> str:
    """
    Return the full corpus as an injection-safe string for LlmAgent instructions.

    Curly braces are replaced with full-width Unicode variants to prevent ADK's
    state-interpolation regex from treating corpus JSON as state references.
    """
    raw = json.dumps(_get_corpus(), indent=2, ensure_ascii=False)
    return raw.replace("{", "｛").replace("}", "｝")
