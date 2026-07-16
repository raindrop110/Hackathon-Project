"""
rag_data_generation — RAG Data Generation sub-system for the hackathon pipeline.

Exposes `root_agent` (a SequentialAgent) as the ADK package entry point.
Run with:
    adk web          (interactive UI)
    adk run rag_data_generation   (single headless run)
    python main.py   (headless runner with printed state output)
"""

from .agent import root_agent

__all__ = ["root_agent"]
