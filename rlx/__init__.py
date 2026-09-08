"""Reconciliation Ledger - a cross-document Fact Knowledge Layer.

Design principle: the LLM proposes, deterministic code decides. No fact enters the
trusted ledger unless its evidence re-verifies against the source PDF.
"""

__version__ = "0.1.0"
PIPELINE_VERSION = "rlx-0.1.0"
