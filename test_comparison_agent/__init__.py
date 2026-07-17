"""
test_comparison_agent — End-to-end evaluation pipeline for the normalization system.

Run with:
    adk web test_comparison_agent
    adk run test_comparison_agent

Optional env var:
    COMPARISON_BATCH_SIZE=10   (default: 10)
"""

from .agent import root_agent

__all__ = ["root_agent"]
