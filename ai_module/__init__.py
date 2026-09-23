"""Public integration contract for contractor selection."""

from .evidence import EVIDENCE_VERSION, build_evidence
from .ranking import PROMPT_VERSION, RECOMMENDATION_VERSION, rank_candidates

__all__ = [
    "build_evidence",
    "rank_candidates",
    "EVIDENCE_VERSION",
    "PROMPT_VERSION",
    "RECOMMENDATION_VERSION",
]
